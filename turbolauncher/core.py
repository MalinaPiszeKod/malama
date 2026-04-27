from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from .models import ModelEntry, detect_quant, file_size_gb, read_cfg
from .paths import (
    APP_DIR,
    HF_CACHE_DIR,
    MODEL_LIBRARY_FILE,
    PRESETS_DIR,
    REGISTRY_FILE,
    RUNTIME_PATH_FILE,
    SESSION_FILE,
    ensure_dirs,
)
from .settings import BUILT_IN_PRESETS

_REGISTRY_LOCK = Lock()


def read_json(path: Path, default: Any = None) -> Any:
    import json

    try:
        with path.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def slugify(name: str) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-")
    return slug or "preset"


def sanitize_alias(name: str, max_len: int = 60) -> str:
    import re

    alias = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    return (alias or "model")[:max_len]


class LauncherCore:
    def __init__(self, runtime_path: str | None = None) -> None:
        ensure_dirs()
        self.runtime_path_arg = runtime_path

    def get_default_download_dir(self) -> Path:
        return HF_CACHE_DIR

    def get_download_dir(self) -> Path:
        raw = read_json(MODEL_LIBRARY_FILE, {}) or {}
        value = raw.get("download_dir")
        if value:
            return Path(value)
        return self.get_default_download_dir()

    def set_download_dir(self, path: str | Path) -> Path:
        resolved = Path(path).expanduser()
        raw = read_json(MODEL_LIBRARY_FILE, {}) or {}
        raw["download_dir"] = str(resolved)
        if "source_dirs" not in raw:
            raw["source_dirs"] = [str(p) for p in self.default_model_source_dirs()]
        write_json(MODEL_LIBRARY_FILE, raw)
        return resolved

    def get_model_source_dirs(self) -> list[str]:
        raw = read_json(MODEL_LIBRARY_FILE, {}) or {}
        values = raw.get("source_dirs")
        if isinstance(values, list):
            return [str(v) for v in values]
        return [str(p) for p in self.default_model_source_dirs()]

    def save_model_source_dirs(self, dirs: list[str | Path]) -> None:
        raw = read_json(MODEL_LIBRARY_FILE, {}) or {}
        raw["source_dirs"] = [str(Path(p)) for p in dirs]
        if "download_dir" not in raw:
            raw["download_dir"] = str(self.get_default_download_dir())
        write_json(MODEL_LIBRARY_FILE, raw)

    def default_model_source_dirs(self) -> list[Path]:
        paths = [
            Path(r"D:\Macius_models\lmstudio-community\Qwen3.6-35B-A3B-GGUF"),
            Path(r"D:\Macius_models\lmstudio-community"),
            Path(r"D:\Macius_models"),
            HF_CACHE_DIR,
            Path.home() / ".cache" / "huggingface",
            APP_DIR,
        ]
        return paths

    def list_presets(self) -> list[dict[str, Any]]:
        presets = [{**preset, "IsBuiltIn": True} for preset in BUILT_IN_PRESETS]
        built_in_files = {p["File"].lower() for p in BUILT_IN_PRESETS}
        for path in sorted(PRESETS_DIR.glob("*.json")):
            if path.name.lower() in built_in_files:
                continue
            data = read_json(path, {}) or {}
            presets.append(
                {
                    "Name": data.get("Name") or path.stem.replace("-", " "),
                    "Description": data.get("Description") or "User preset",
                    "File": path.name,
                    "IsBuiltIn": False,
                }
            )
        return presets

    def load_preset(self, name: str) -> dict[str, Any] | None:
        for preset in BUILT_IN_PRESETS:
            if preset["Name"] == name:
                data = read_json(PRESETS_DIR / preset["File"], None)
                if data:
                    data["IsBuiltIn"] = True
                return data
        candidate = PRESETS_DIR / f"{slugify(name)}.json"
        if candidate.exists():
            data = read_json(candidate, None)
            if data:
                data["IsBuiltIn"] = False
            return data
        for path in PRESETS_DIR.glob("*.json"):
            data = read_json(path, None)
            if data and data.get("Name") == name:
                data["IsBuiltIn"] = path.name in {p["File"] for p in BUILT_IN_PRESETS}
                return data
        return None

    def save_preset(
        self, name: str, description: str, settings: dict[str, Any]
    ) -> Path:
        path = PRESETS_DIR / f"{slugify(name)}.json"
        write_json(
            path,
            {
                "Name": name,
                "Description": description,
                "Created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "Settings": settings,
            },
        )
        return path

    def load_session(self) -> dict[str, Any] | None:
        return read_json(SESSION_FILE, None)

    def save_session(
        self, preset_name: str, model_path: str | None, settings: dict[str, Any]
    ) -> None:
        data = dict(settings)
        data["LastPreset"] = preset_name
        data["LastModel"] = model_path or ""
        data["PresetName"] = preset_name
        data["ModelPath"] = model_path or ""
        data["Settings"] = dict(settings)
        data["SavedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        write_json(SESSION_FILE, data)

    def get_model_registry(self) -> OrderedDict[str, str]:
        registry: OrderedDict[str, str] = OrderedDict()
        if not REGISTRY_FILE.exists():
            return registry
        try:
            for raw_line in REGISTRY_FILE.read_text(
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
        REGISTRY_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def add_model_to_registry(
        self, alias: str, model_or_config_path: str | Path
    ) -> None:
        with _REGISTRY_LOCK:
            registry = self.get_model_registry()
            registry[sanitize_alias(alias)] = str(model_or_config_path)
            self.save_model_registry(registry)

    def resolve_model_entry(
        self, alias: str, entry_path: str | Path
    ) -> ModelEntry | None:
        resolved = Path(entry_path)
        if not resolved.is_absolute():
            resolved = APP_DIR / resolved
        if resolved.suffix.lower() == ".cfg" and resolved.exists():
            cfg = read_cfg(resolved)
            model_path = cfg.get("MODEL_PATH")
            if model_path:
                next_path = Path(model_path)
                resolved = (
                    next_path
                    if next_path.is_absolute()
                    else (resolved.parent / next_path)
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
        )

    def common_model_dirs(self) -> list[Path]:
        paths = [Path(p).expanduser() for p in self.get_model_source_dirs()]
        for value in self.get_model_registry().values():
            path = Path(value)
            if not path.is_absolute():
                path = APP_DIR / path
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

    def read_runtime_path(self) -> str:
        try:
            return RUNTIME_PATH_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def set_runtime_path(self, path: str | Path) -> None:
        RUNTIME_PATH_FILE.write_text(str(path).strip(), encoding="utf-8")

    def resolve_runtime_executable(self) -> Path | None:
        candidates: list[Path] = []
        if self.runtime_path_arg:
            candidates.append(Path(self.runtime_path_arg))
        saved = self.read_runtime_path()
        if saved:
            candidates.append(Path(saved))
        candidates += [
            APP_DIR.parent / "llama-server.exe",
            APP_DIR / "llama-server.exe",
        ]
        for candidate in candidates:
            try:
                candidate = candidate.expanduser().resolve()
            except OSError:
                candidate = candidate.expanduser()
            if candidate.exists() and candidate.is_file():
                return candidate
        return None
