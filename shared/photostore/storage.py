import shutil
from typing import Protocol
from pathlib import Path
from pathlib import PurePosixPath

from .config import settings


class InvalidStorageKey(ValueError):
    pass


class StorageConfigurationError(RuntimeError):
    pass


class StorageBackend(Protocol):
    is_local: bool

    def local_path(self, key: str) -> Path: ...
    def exists(self, key: str) -> bool: ...
    def download_to_file(self, key: str, destination: str | Path) -> None: ...
    def upload_file(
        self,
        source: str | Path,
        key: str,
        content_type: str | None = None,
    ) -> None: ...
    def delete(self, key: str) -> None: ...
    def presigned_get_url(
        self,
        key: str,
        expires_seconds: int = 3600,
        response_content_disposition: str | None = None,
        response_content_type: str | None = None,
    ) -> str: ...


def normalize_storage_key(key: str) -> str:
    cleaned = key.replace("\\", "/").strip("/")
    path = PurePosixPath(cleaned)
    if not cleaned or path.is_absolute() or ".." in path.parts:
        raise InvalidStorageKey(f"Invalid storage key: {key}")
    return path.as_posix()


class LocalStorageBackend:
    is_local = True

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or settings.STORAGE_ROOT)

    def local_path(self, key: str) -> Path:
        key = normalize_storage_key(key)
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

    def presigned_get_url(
        self,
        key: str,
        expires_seconds: int = 3600,
        response_content_disposition: str | None = None,
        response_content_type: str | None = None,
    ) -> str:
        raise NotImplementedError("Local storage is served through application routes")


class R2StorageBackend:
    is_local = False

    def __init__(
        self,
        bucket: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region_name: str | None = None,
    ) -> None:
        self.bucket = bucket or settings.R2_BUCKET
        self.endpoint_url = endpoint_url or settings.R2_ENDPOINT_URL
        self.access_key_id = access_key_id or settings.R2_ACCESS_KEY_ID
        self.secret_access_key = secret_access_key or settings.R2_SECRET_ACCESS_KEY
        self.region_name = region_name or settings.R2_REGION
        if not self.endpoint_url and settings.R2_ACCOUNT_ID:
            self.endpoint_url = (
                f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
            )
        if not all(
            [
                self.bucket,
                self.endpoint_url,
                self.access_key_id,
                self.secret_access_key,
            ]
        ):
            raise StorageConfigurationError("R2 storage is not fully configured")
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:
                raise RuntimeError(
                    "boto3 is required when STORAGE_BACKEND=r2"
                ) from exc

            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region_name,
            )
        return self._client

    def local_path(self, key: str) -> Path:
        raise NotImplementedError("R2 objects do not have local paths")

    def exists(self, key: str) -> bool:
        key = normalize_storage_key(key)
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception as exc:
            code = (
                getattr(exc, "response", {})
                .get("Error", {})
                .get("Code")
            )
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def download_to_file(self, key: str, destination: str | Path) -> None:
        key = normalize_storage_key(key)
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(destination))

    def upload_file(
        self,
        source: str | Path,
        key: str,
        content_type: str | None = None,
    ) -> None:
        key = normalize_storage_key(key)
        extra_args = {"ContentType": content_type} if content_type else None
        if extra_args:
            self.client.upload_file(str(source), self.bucket, key, ExtraArgs=extra_args)
        else:
            self.client.upload_file(str(source), self.bucket, key)

    def delete(self, key: str) -> None:
        key = normalize_storage_key(key)
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_get_url(
        self,
        key: str,
        expires_seconds: int = 3600,
        response_content_disposition: str | None = None,
        response_content_type: str | None = None,
    ) -> str:
        key = normalize_storage_key(key)
        params = {"Bucket": self.bucket, "Key": key}
        if response_content_disposition:
            params["ResponseContentDisposition"] = response_content_disposition
        if response_content_type:
            params["ResponseContentType"] = response_content_type
        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_seconds,
        )


def _storage_backend_for_name(backend: str) -> StorageBackend:
    backend = backend.strip().lower()
    if backend == "local":
        return LocalStorageBackend()
    if backend == "r2":
        return R2StorageBackend()
    raise ValueError(f"Unsupported storage backend: {backend}")


def get_storage_backend() -> StorageBackend:
    return _storage_backend_for_name(settings.STORAGE_BACKEND)


def get_zip_storage_backend_name() -> str:
    explicit_backend = settings.ZIP_STORAGE_BACKEND.strip()
    legacy_backend = settings.STORAGE_BACKEND.strip()
    return (explicit_backend or legacy_backend or "local").lower()


def get_zip_storage_backend() -> StorageBackend:
    return _storage_backend_for_name(get_zip_storage_backend_name())
