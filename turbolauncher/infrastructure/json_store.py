from __future__ import annotations

from pathlib import Path
from typing import Any


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
