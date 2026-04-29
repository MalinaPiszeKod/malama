from __future__ import annotations

import os
from pathlib import Path

MODEL_SOURCE_DIRS_ENV_VAR = "TURBOLAUNCHER_MODEL_SOURCE_DIRS"


LEGACY_DEFAULT_MODEL_SOURCE_DIRS = [
    Path(r"D:\Macius_models\lmstudio-community\Qwen3.6-35B-A3B-GGUF"),
    Path(r"D:\Macius_models\lmstudio-community"),
    Path(r"D:\Macius_models"),
]


def _split_env_paths(raw_value: str) -> list[Path]:
    return [Path(value).expanduser() for value in raw_value.split(os.pathsep) if value.strip()]


def default_model_source_dirs(app_dir: Path, hf_cache_dir: Path) -> list[Path]:
    paths: list[Path] = []
    env_value = os.environ.get(MODEL_SOURCE_DIRS_ENV_VAR, "").strip()
    if env_value:
        paths.extend(_split_env_paths(env_value))
    paths.extend(
        [
            *LEGACY_DEFAULT_MODEL_SOURCE_DIRS,
            hf_cache_dir,
            Path.home() / ".cache" / "huggingface",
            app_dir,
        ]
    )

    deduped: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path).lower()
        if key not in seen:
            deduped.append(path)
            seen.add(key)
    return deduped
