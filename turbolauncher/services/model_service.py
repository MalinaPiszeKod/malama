from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from ..infrastructure.json_store import read_json, write_json
from ..models import ModelEntry, file_size_gb, parse_cfg_bool, parse_cfg_int, read_cfg
from ..model_sources import default_model_source_dirs

_REGISTRY_LOCK = Lock()


def slugify(name: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-")
    return slug or "preset"


def sanitize_alias(name: str, max_len: int = 60) -> str:
    import re

    alias = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    return (alias or "model")[:max_len]


def _model_config_fields(config_path: Path | None, cfg: dict[str, str]) -> dict[str, Any]:
    transformer_layers = parse_cfg_int(cfg.get("TRANSFORMER_LAYERS"))
    output_layer = parse_cfg_bool(cfg.get("OUTPUT_LAYER"))
    full_offload_layers = parse_cfg_int(cfg.get("FULL_OFFLOAD_LAYERS"))
    if full_offload_layers is None and transformer_layers is not None:
        full_offload_layers = transformer_layers + (0 if output_layer is False else 1)
    return {
        "config_path": config_path,
        "sys_prompt": cfg.get("CHAT_SYS_PROMPT", ""),
        "chat_template": cfg.get("CHAT_TEMPLATE") or cfg.get("PROMPT_TEMPLATE", ""),
        "transformer_layers": transformer_layers,
        "output_layer": output_layer,
        "full_offload_layers": full_offload_layers,
    }


class ModelService:
    def __init__(
        self,
        *,
        app_dir: Path,
        hf_cache_dir: Path,
        model_library_file: Path,
        model_configs_dir: Path,
        registry_file: Path,
    ) -> None:
        self.app_dir = app_dir
        self.hf_cache_dir = hf_cache_dir
        self.model_library_file = model_library_file
        self.model_configs_dir = model_configs_dir
        self.registry_file = registry_file

    def get_default_download_dir(self) -> Path:
        return self.hf_cache_dir

    def get_download_dir(self) -> Path:
        raw = read_json(self.model_library_file, {}) or {}
        value = raw.get("download_dir")
        if value:
            return Path(value)
        return self.get_default_download_dir()

    def set_download_dir(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser()
        raw = read_json(self.model_library_file, {}) or {}
        raw["download_dir"] = str(resolved)
        if "source_dirs" not in raw:
            raw["source_dirs"] = [str(p) for p in self.default_model_source_dirs()]
        write_json(self.model_library_file, raw)
        return resolved

    def get_model_source_dirs(self) -> list[str]:
        raw = read_json(self.model_library_file, {}) or {}
        values = raw.get("source_dirs")
        if isinstance(values, list):
            return [str(v) for v in values]
        return [str(p) for p in self.default_model_source_dirs()]

    def save_model_source_dirs(self, dirs: list[str | Path]) -> None:
        raw = read_json(self.model_library_file, {}) or {}
        raw["source_dirs"] = [str(Path(p)) for p in dirs]
        if "download_dir" not in raw:
            raw["download_dir"] = str(self.get_default_download_dir())
        write_json(self.model_library_file, raw)

    def default_model_source_dirs(self) -> list[Path]:
        return default_model_source_dirs(self.app_dir, self.hf_cache_dir)

    def get_model_registry(self) -> OrderedDict[str, str]:
        registry: OrderedDict[str, str] = OrderedDict()
        if not self.registry_file.exists():
            return registry
        try:
            for raw_line in self.registry_file.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                alias, path = line.split("=", 1)
                alias = alias.strip()
                path = path.split("#", 1)[0].strip()
                if alias and path:
                    registry[alias] = path
        except OSError:
            pass
        return registry

    def save_model_registry(self, registry: OrderedDict[str, str]) -> None:
        lines = ["# Model registry - alias=config_path", "# No spaces around =", ""] + [
            f"{alias}={path}" for alias, path in registry.items()
        ]
        self.registry_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def add_model_to_registry(self, alias: str, model_or_config_path: str | Path) -> None:
        with _REGISTRY_LOCK:
            registry = self.get_model_registry()
            registry[sanitize_alias(alias)] = str(model_or_config_path)
            self.save_model_registry(registry)

    def resolve_model_entry(self, alias: str, entry_path: str | Path) -> ModelEntry | None:
        config_path: Path | None = None
        sys_prompt = ""
        chat_template = ""
        fields: dict[str, Any] = {}
        resolved = Path(entry_path)
        if not resolved.is_absolute():
            resolved = self.app_dir / resolved
        if resolved.suffix.lower() == ".cfg" and resolved.exists():
            cfg = read_cfg(resolved)
            fields = _model_config_fields(resolved, cfg)
            config_path = fields["config_path"]
            sys_prompt = fields["sys_prompt"]
            chat_template = fields["chat_template"]
            model_path = cfg.get("MODEL_PATH")
            if model_path:
                next_path = Path(model_path)
                resolved = (
                    next_path if next_path.is_absolute() else (resolved.parent / next_path)
                )
            if cfg.get("ALIAS"):
                alias = cfg["ALIAS"]
        try:
            resolved = resolved.expanduser().resolve()
        except OSError:
            resolved = resolved.expanduser()
        if not resolved.exists() or resolved.suffix.lower() != ".gguf":
            return None
        return ModelEntry(
            path=resolved,
            name=resolved.stem,
            size_gb=file_size_gb(resolved),
            alias=alias,
            directory=resolved.parent.name,
            sys_prompt=sys_prompt,
            chat_template=chat_template,
            config_path=config_path,
            transformer_layers=fields.get("transformer_layers"),
            output_layer=fields.get("output_layer"),
            full_offload_layers=fields.get("full_offload_layers"),
        )

    def _model_config_for_path(self, path: Path) -> tuple[Path | None, dict[str, str]]:
        candidates = [self.model_configs_dir / f"{path.stem}.cfg", path.with_suffix(".cfg")]
        for candidate in candidates:
            if candidate.exists():
                return candidate, read_cfg(candidate)
        return None, {}

    def common_model_dirs(self) -> list[Path]:
        paths = [Path(p).expanduser() for p in self.get_model_source_dirs()]
        for value in self.get_model_registry().values():
            path = Path(value)
            if not path.is_absolute():
                path = self.app_dir / path
            if path.suffix.lower() == ".cfg" and path.exists():
                cfg = read_cfg(path)
                model_path = cfg.get("MODEL_PATH")
                if model_path:
                    path = Path(model_path)
            if path.suffix.lower() == ".gguf":
                paths.append(path.parent)

        deduped: list[Path] = []
        seen: set[str] = set()
        for path in paths:
            key = str(path).lower()
            if key not in seen:
                deduped.append(path)
                seen.add(key)
        return deduped

    def load_models_with_report(self) -> tuple[list[ModelEntry], list[str]]:
        models: list[ModelEntry] = []
        report: list[str] = ["Scanning model source folders..."]
        seen_paths: set[str] = set()

        for alias, path in self.get_model_registry().items():
            model = self.resolve_model_entry(alias, path)
            if model:
                key = str(model.path).lower()
                if key in seen_paths:
                    report.append(f"Duplicate registry model skipped: {model.path}")
                    continue
                models.append(model)
                seen_paths.add(key)
                report.append(f"Loaded registry model: {alias} -> {model.path}")
            else:
                report.append(
                    f"Skipped registry model: {alias} -> {path} (missing file or not a GGUF)"
                )

        for base in self.common_model_dirs():
            raw = str(base)
            base = Path(raw).expanduser()
            if not base.exists() or not base.is_dir():
                report.append(f"Skipped missing source folder: {base}")
                continue

            found_count = 0
            added_count = 0
            for path in self.iter_gguf_files(base):
                found_count += 1
                try:
                    resolved = path.resolve()
                except OSError:
                    resolved = path
                key = str(resolved).lower()
                if key in seen_paths:
                    report.append(f"Duplicate model skipped: {resolved}")
                    continue
                seen_paths.add(key)
                added_count += 1
                alias = resolved.stem.replace("-", " ").replace("_", " ").strip()
                models.append(
                    ModelEntry(
                        path=resolved,
                        name=resolved.stem,
                        size_gb=file_size_gb(resolved),
                        alias=alias,
                        directory=resolved.parent.name,
                        **_model_config_fields(*self._model_config_for_path(resolved)),
                    )
                )
            report.append(
                f"Found {found_count} GGUF file(s) in {base}; added {added_count} new model(s)."
            )
        return sorted(models, key=lambda m: (m.alias.lower(), m.name.lower())), report

    def iter_gguf_files(self, base: Path, limit: int = 1000) -> Iterable[Path]:
        if not base.exists() or not base.is_dir():
            return
        count = 0
        try:
            for path in base.rglob("*.gguf"):
                if path.name.lower().startswith("mmproj"):
                    continue
                count += 1
                yield path
                if count >= limit:
                    return
        except OSError:
            return

    def load_models(self) -> list[ModelEntry]:
        models, _ = self.load_models_with_report()
        return models
