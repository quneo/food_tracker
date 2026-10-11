"""Object storage: MinIO through the S3 API, or memory for tests."""

import io
import logging
from functools import lru_cache
from typing import Protocol

from app.config import get_settings

log = logging.getLogger(__name__)


class StorageError(Exception):
    pass


class Storage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def keys(self, prefix: str) -> list[str]: ...


class S3Storage:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str, secure: bool):
        from minio import Minio

        self.client = Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)
        self.bucket = bucket
        self._ready = False

    def _bucket(self):
        if self._ready:
            return
        # New buckets are private: no anonymous policy is ever set.
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        self._ready = True

    def _call(self, action, *args, **kwargs):
        from minio.error import MinioException

        try:
            self._bucket()
            return action(*args, **kwargs)
        except (MinioException, OSError) as error:
            raise StorageError(str(error)) from error

    def put(self, key, data, content_type):
        self._call(
            self.client.put_object,
            self.bucket,
            key,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
        )

    def get(self, key):
        def read():
            response = self.client.get_object(self.bucket, key)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return self._call(read)

    def delete(self, key):
        self._call(self.client.remove_object, self.bucket, key)

    def keys(self, prefix):
        return self._call(
            lambda: [
                item.object_name
                for item in self.client.list_objects(self.bucket, prefix=prefix, recursive=True)
            ]
        )

    def delete_prefix(self, prefix):
        from minio.deleteobjects import DeleteObject

        keys = self.keys(prefix)
        errors = self._call(
            lambda: list(
                self.client.remove_objects(self.bucket, (DeleteObject(key) for key in keys))
            )
        )
        if errors:
            raise StorageError(f"{len(errors)} objects not deleted under {prefix}")


class MemoryStorage:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key, data, content_type):
        self.objects[key] = (data, content_type)

    def get(self, key):
        try:
            return self.objects[key][0]
        except KeyError:
            raise StorageError(f"no object {key}") from None

    def delete(self, key):
        self.objects.pop(key, None)

    def keys(self, prefix):
        return [key for key in self.objects if key.startswith(prefix)]

    def delete_prefix(self, prefix):
        for key in self.keys(prefix):
            del self.objects[key]


@lru_cache
def get_storage() -> Storage:
    settings = get_settings()
    return S3Storage(
        settings.s3_endpoint,
        settings.s3_access_key,
        settings.s3_secret_key,
        settings.s3_bucket,
        settings.s3_secure,
    )
