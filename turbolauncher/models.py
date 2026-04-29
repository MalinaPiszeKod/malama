from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import GB


def detect_quant(path_or_name: str) -> str:
    name = Path(path_or_name).stem.upper()
    if "Q6_K" in name:
        return "Q6_K"
    if "Q8_0" in name:
        return "Q8_0"
    if "Q5_K" in name:
        return "Q5_K_M"
    if "Q4_K" in name:
        return "Q4_K_M"
    if "UD-Q3_XXS" in name:
        return "UD-Q3_XXS"
    return "Unknown"


def file_size_gb(path: Path) -> float:
    try:
        return round(path.stat().st_size / GB, 1)
    except OSError:
        return 0.0


def read_cfg(path: Path) -> dict[str, str]:
    cfg: dict[str, str] = {}
    try:
        for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            cfg[key.strip()] = value.strip()
    except OSError:
        pass
    return cfg


def parse_cfg_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError, AttributeError):
        return None


def parse_cfg_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"on", "true", "1"}:
        return True
    if normalized in {"off", "false", "0"}:
        return False
    return None


@dataclass(frozen=True)
class ModelEntry:
    path: Path
    name: str
    size_gb: float
    alias: str
    directory: str
    sys_prompt: str = ""
    chat_template: str = ""
    config_path: Path | None = None
    transformer_layers: int | None = None
    output_layer: bool | None = None
    full_offload_layers: int | None = None

    @property
    def quant(self) -> str:
        return detect_quant(self.path.name)

    @property
    def display_name(self) -> str:
        size = f"{self.size_gb:g} GB" if self.size_gb else "? GB"
        quant = self.quant
        quant_text = f"{quant} · " if quant != "Unknown" else ""
        return f"{self.alias}  ·  {quant_text}{self.name}  ({size})"
