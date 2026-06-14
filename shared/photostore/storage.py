import shutil
from pathlib import Path

from .config import settings


class LocalStorageBackend:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.STORAGE_ROOT)

    def local_path(self, key: str) -> Path:
        root = self.root.resolve()
        target = (root / key).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            raise ValueError(f"Storage key escapes root: {key}")
        return target

    def exists(self, key: str) -> bool:
        return self.local_path(key).exists()

    def download_to_file(self, key: str, destination: str | Path) -> None:
        shutil.copy2(self.local_path(key), destination)

    def upload_file(
        self,
        source: str | Path,
        key: str,
        content_type: str | None = None,
    ) -> None:
        destination = self.local_path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        tmp_destination = destination.with_name(f".{destination.name}.tmp")
        shutil.copy2(source, tmp_destination)
        tmp_destination.replace(destination)
        destination.chmod(0o644)

    def delete(self, key: str) -> None:
        self.local_path(key).unlink(missing_ok=True)

    def presigned_get_url(self, key: str, expires_seconds: int = 3600) -> str:
        raise NotImplementedError("Local storage is served through application routes")


def get_storage_backend() -> LocalStorageBackend:
    return LocalStorageBackend()
