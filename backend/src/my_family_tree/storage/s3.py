"""S3-compatible object storage. Uses boto3 with path-style addressing so the
same code works against MinIO (local) and S3 (prod). All keys are namespaced
under `tree/{tree_id}/...` (see plan)."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import IO, Any

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from my_family_tree.core.config import S3Settings
from my_family_tree.core.errors import StorageError
from my_family_tree.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class StoredObject:
    bucket: str
    key: str
    size: int
    sha256: str
    etag: str


class ObjectStore:
    """Thin wrapper around boto3. Synchronous boto calls are run in a thread to
    keep the async event loop responsive."""

    def __init__(self, *, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self._client = client

    async def ensure_bucket(self) -> None:
        """Create the bucket if it doesn't exist. No-op if it does."""
        try:
            await asyncio.to_thread(self._client.head_bucket, Bucket=self.bucket)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchBucket"}:
                await asyncio.to_thread(self._client.create_bucket, Bucket=self.bucket)
                log.info("storage.bucket_created", bucket=self.bucket)
            else:
                raise StorageError(f"head_bucket failed: {e}") from e

    async def put(
        self,
        key: str,
        body: bytes | IO[bytes],
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        data = body if isinstance(body, bytes) else body.read()
        sha256 = hashlib.sha256(data).hexdigest()
        kwargs: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": key,
            "Body": data,
            "ContentType": content_type,
        }
        if metadata:
            kwargs["Metadata"] = metadata
        resp = await asyncio.to_thread(self._client.put_object, **kwargs)
        return StoredObject(
            bucket=self.bucket,
            key=key,
            size=len(data),
            sha256=sha256,
            etag=resp.get("ETag", "").strip('"'),
        )

    async def get(self, key: str) -> bytes:
        try:
            resp = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        except ClientError as e:
            raise StorageError(f"get_object {key} failed: {e}") from e
        return await asyncio.to_thread(resp["Body"].read)

    async def stream(self, key: str, *, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        """Stream an object in chunks. Yields bytes."""
        try:
            resp = await asyncio.to_thread(self._client.get_object, Bucket=self.bucket, Key=key)
        except ClientError as e:
            raise StorageError(f"get_object {key} failed: {e}") from e

        body = resp["Body"]
        while True:
            chunk = await asyncio.to_thread(body.read, chunk_size)
            if not chunk:
                break
            yield chunk

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._client.delete_object, Bucket=self.bucket, Key=key)

    async def head(self, key: str) -> dict[str, Any] | None:
        try:
            resp = await asyncio.to_thread(self._client.head_object, Bucket=self.bucket, Key=key)
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code")
            if code in {"404", "NoSuchKey"}:
                return None
            raise StorageError(f"head_object {key} failed: {e}") from e
        return dict(resp)

    async def presign(
        self,
        key: str,
        *,
        expires_in_s: int = 3600,
        method: str = "get_object",
    ) -> str:
        return await asyncio.to_thread(
            self._client.generate_presigned_url,
            ClientMethod=method,
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in_s,
        )


def build_object_store(s3: S3Settings) -> ObjectStore:
    """Build an ObjectStore from settings.

    `endpoint_url` set + `force_path_style` true drives MinIO. Real S3 leaves
    `endpoint_url` blank (None) and uses virtual-hosted-style by default.
    """
    config = Config(
        signature_version="s3v4",
        s3={"addressing_style": "path" if s3.force_path_style else "auto"},
    )
    client = boto3.client(
        "s3",
        endpoint_url=s3.endpoint_url,
        region_name=s3.region,
        aws_access_key_id=s3.access_key.get_secret_value(),
        aws_secret_access_key=s3.secret_key.get_secret_value(),
        config=config,
    )
    return ObjectStore(bucket=s3.bucket_documents, client=client)


def storage_key(tree_id: str, sha256: str, ext: str) -> str:
    """Canonical originals key. Sharded by sha256 prefix to avoid hot keys."""
    ext_clean = ext.lstrip(".") or "bin"
    return f"tree/{tree_id}/originals/{sha256[:2]}/{sha256}.{ext_clean}"


def derived_key(tree_id: str, document_id: str, suffix: str) -> str:
    return f"tree/{tree_id}/derived/{document_id}/{suffix}"
