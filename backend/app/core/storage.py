from pathlib import Path, PurePosixPath

from app.config import get_settings


class StorageManager:
    def __init__(self, root: str | None = None):
        self.root = Path(root or get_settings().STORAGE_ROOT)

    def session_dir(self, session_id: str) -> str:
        directory = self.root / "uploads" / session_id
        directory.mkdir(parents=True, exist_ok=True)
        return self._to_relative(directory)

    def save_upload(self, session_id: str, filename: str, data: bytes) -> str:
        directory = self.root / "uploads" / session_id
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / filename
        file_path.write_bytes(data)
        return self._to_relative(file_path)

    def step_path(self, session_id: str, order: int, name: str) -> str:
        directory = self.root / "steps" / session_id
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / f"{order:02d}_{name}"
        return self._to_relative(file_path)

    @staticmethod
    def _to_relative(path: Path) -> str:
        return str(PurePosixPath(*path.parts))
