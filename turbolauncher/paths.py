from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "TurboLauncher"
APP_DIR = Path(__file__).resolve().parent.parent
PRESETS_DIR = APP_DIR / "presets"
MODEL_CONFIGS_DIR = APP_DIR / "model-configs"
REGISTRY_FILE = APP_DIR / "models.registry"
APPDATA_ROOT = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
SESSION_DIR = APPDATA_ROOT / APP_NAME
SESSION_FILE = SESSION_DIR / "session.json"
RUNTIME_PATH_FILE = SESSION_DIR / "runtime_path.txt"
MODEL_LIBRARY_FILE = SESSION_DIR / "model_library.json"
LOG_FILE = SESSION_DIR / "launcher.log"
HF_CACHE_DIR = Path.home() / ".cache" / "huggingface" / "hf_download"
GB = 1024**3


def ensure_dirs() -> None:
    PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    MODEL_CONFIGS_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
