from __future__ import annotations

from pathlib import Path


class RuntimeService:
    def __init__(
        self, runtime_path_file: Path, app_dir: Path, runtime_path: str | None = None
    ) -> None:
        self.runtime_path_file = runtime_path_file
        self.app_dir = app_dir
        self.runtime_path = runtime_path

    def read_runtime_path(self) -> str:
        try:
            return self.runtime_path_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def set_runtime_path(self, path: str | Path) -> None:
        self.runtime_path_file.write_text(str(path).strip(), encoding="utf-8")

    def resolve_runtime_executable(self) -> Path | None:
        candidates: list[Path] = []
        if self.runtime_path:
            candidates.append(Path(self.runtime_path))
        saved = self.read_runtime_path()
        if saved:
            candidates.append(Path(saved))
        candidates += [
            self.app_dir.parent / "llama-server.exe",
            self.app_dir / "llama-server.exe",
        ]
        for candidate in candidates:
            try:
                candidate = candidate.expanduser().resolve()
            except OSError:
                candidate = candidate.expanduser()
            if candidate.exists() and candidate.is_file():
                return candidate
        return None
