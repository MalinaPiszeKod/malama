from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..infrastructure.json_store import read_json, write_json


class SessionService:
    def __init__(self, session_file: Path) -> None:
        self.session_file = session_file

    def load_session(self) -> dict[str, Any] | None:
        return read_json(self.session_file, None)

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
        write_json(self.session_file, data)
