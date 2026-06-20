import os


def _storage_module():
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://test:test@localhost/test")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

    import photostore.storage as storage

    return storage


def test_zip_storage_backend_falls_back_to_legacy_storage_backend(monkeypatch):
    storage = _storage_module()
    from photostore.config import settings

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "r2")
    monkeypatch.setattr(settings, "ZIP_STORAGE_BACKEND", "")
    monkeypatch.setattr(settings, "R2_ACCOUNT_ID", "acct_test")
    monkeypatch.setattr(settings, "R2_ACCESS_KEY_ID", "key_test")
    monkeypatch.setattr(settings, "R2_SECRET_ACCESS_KEY", "secret_test")
    monkeypatch.setattr(settings, "R2_BUCKET", "photostore")
    monkeypatch.setattr(settings, "R2_ENDPOINT_URL", "")

    backend = storage.get_zip_storage_backend()

    assert storage.get_zip_storage_backend_name() == "r2"
    assert isinstance(backend, storage.R2StorageBackend)


def test_zip_storage_backend_overrides_legacy_storage_backend(monkeypatch):
    storage = _storage_module()
    from photostore.config import settings

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "r2")
    monkeypatch.setattr(settings, "ZIP_STORAGE_BACKEND", "local")

    backend = storage.get_zip_storage_backend()

    assert storage.get_zip_storage_backend_name() == "local"
    assert isinstance(backend, storage.LocalStorageBackend)
