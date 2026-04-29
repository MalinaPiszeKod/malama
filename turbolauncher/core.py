from __future__ import annotations

from pathlib import Path
from typing import Any

from .infrastructure.json_store import read_json, write_json
from .paths import (
    APP_DIR,
    HF_CACHE_DIR,
    MODEL_CONFIGS_DIR,
    MODEL_LIBRARY_FILE,
    PRESETS_DIR,
    REGISTRY_FILE,
    RUNTIME_PATH_FILE,
    SESSION_FILE,
    ensure_dirs,
)
from .services.model_service import ModelService, sanitize_alias, slugify
from .services.preset_service import PresetService
from .services.runtime_service import RuntimeService
from .services.session_service import SessionService
from .settings import BUILT_IN_PRESETS


class LauncherCore:
    """Compatibility facade over focused services.

    Keeps the public API stable while separating presets, sessions, runtime
    resolution, and model discovery into independent service modules.
    """

    def __init__(self, runtime_path: str | None = None) -> None:
        ensure_dirs()
        self.runtime_path_arg = runtime_path
        self.model_service = ModelService(
            app_dir=APP_DIR,
            hf_cache_dir=HF_CACHE_DIR,
            model_library_file=MODEL_LIBRARY_FILE,
            model_configs_dir=MODEL_CONFIGS_DIR,
            registry_file=REGISTRY_FILE,
        )
        self.preset_service = PresetService(PRESETS_DIR, BUILT_IN_PRESETS)
        self.session_service = SessionService(SESSION_FILE)
        self.runtime_service = RuntimeService(RUNTIME_PATH_FILE, APP_DIR, runtime_path)

    def get_default_download_dir(self) -> Path:
        return self.model_service.get_default_download_dir()

    def get_download_dir(self) -> Path:
        return self.model_service.get_download_dir()

    def set_download_dir(self, path: str | Path) -> Path:
        return self.model_service.set_download_dir(path)

    def get_model_source_dirs(self) -> list[str]:
        return self.model_service.get_model_source_dirs()

    def save_model_source_dirs(self, dirs: list[str | Path]) -> None:
        self.model_service.save_model_source_dirs(dirs)

    def default_model_source_dirs(self) -> list[Path]:
        return self.model_service.default_model_source_dirs()

    def list_presets(self) -> list[dict[str, Any]]:
        return self.preset_service.list_presets()

    def load_preset(self, name: str) -> dict[str, Any] | None:
        return self.preset_service.load_preset(name)

    def save_preset(self, name: str, description: str, settings: dict[str, Any]) -> Path:
        return self.preset_service.save_preset(name, description, settings)

    def load_session(self) -> dict[str, Any] | None:
        return self.session_service.load_session()

    def save_session(
        self, preset_name: str, model_path: str | None, settings: dict[str, Any]
    ) -> None:
        self.session_service.save_session(preset_name, model_path, settings)

    def get_model_registry(self):
        return self.model_service.get_model_registry()

    def save_model_registry(self, registry) -> None:
        self.model_service.save_model_registry(registry)

    def add_model_to_registry(self, alias: str, model_or_config_path: str | Path) -> None:
        self.model_service.add_model_to_registry(alias, model_or_config_path)

    def resolve_model_entry(self, alias: str, entry_path: str | Path):
        return self.model_service.resolve_model_entry(alias, entry_path)

    def common_model_dirs(self) -> list[Path]:
        return self.model_service.common_model_dirs()

    def load_models_with_report(self):
        return self.model_service.load_models_with_report()

    def iter_gguf_files(self, base: Path, limit: int = 1000):
        return self.model_service.iter_gguf_files(base, limit)

    def load_models(self):
        return self.model_service.load_models()

    def read_runtime_path(self) -> str:
        return self.runtime_service.read_runtime_path()

    def set_runtime_path(self, path: str | Path) -> None:
        self.runtime_service.set_runtime_path(path)

    def resolve_runtime_executable(self) -> Path | None:
        return self.runtime_service.resolve_runtime_executable()


__all__ = [
    "LauncherCore",
    "sanitize_alias",
    "slugify",
    "read_json",
    "write_json",
]
