from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..infrastructure.json_store import read_json, write_json


class PresetService:
    def __init__(self, presets_dir: Path, built_in_presets: list[dict[str, Any]]) -> None:
        self.presets_dir = presets_dir
        self.built_in_presets = built_in_presets

    def list_presets(self) -> list[dict[str, Any]]:
        presets = [{**preset, "IsBuiltIn": True} for preset in self.built_in_presets]
        built_in_files = {p["File"].lower() for p in self.built_in_presets}
        for path in sorted(self.presets_dir.glob("*.json")):
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
        for preset in self.built_in_presets:
            if preset["Name"] == name:
                data = read_json(self.presets_dir / preset["File"], None)
                if data:
                    data["IsBuiltIn"] = True
                return data
        candidate = self.presets_dir / f"{self._slugify(name)}.json"
        if candidate.exists():
            data = read_json(candidate, None)
            if data:
                data["IsBuiltIn"] = False
            return data
        for path in self.presets_dir.glob("*.json"):
            data = read_json(path, None)
            if data and data.get("Name") == name:
                data["IsBuiltIn"] = path.name in {p["File"] for p in self.built_in_presets}
                return data
        return None

    def save_preset(
        self, name: str, description: str, settings: dict[str, Any]
    ) -> Path:
        path = self.presets_dir / f"{self._slugify(name)}.json"
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

    @staticmethod
    def _slugify(name: str) -> str:
        import re

        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip()).strip("-")
        return slug or "preset"
