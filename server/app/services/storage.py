import asyncio
from io import BytesIO

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings

settings = get_settings()
_client: Minio | None = None


def get_minio() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    return _client


def ensure_buckets_sync() -> None:
    client = get_minio()
    for bucket in (
        settings.minio_document_bucket,
        settings.minio_ticket_bucket,
    ):
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)


async def ensure_buckets() -> None:
    await asyncio.to_thread(ensure_buckets_sync)


def minio_health_sync() -> None:
    ensure_buckets_sync()


async def minio_health() -> None:
    await asyncio.to_thread(minio_health_sync)


def put_bytes(
    bucket: str,
    object_key: str,
    data: bytes,
    content_type: str,
) -> None:
    get_minio().put_object(
        bucket,
        object_key,
        BytesIO(data),
        length=len(data),
        content_type=content_type,
    )


async def put_bytes_async(
    bucket: str,
    object_key: str,
    data: bytes,
    content_type: str,
) -> None:
    await asyncio.to_thread(put_bytes, bucket, object_key, data, content_type)


def get_bytes(bucket: str, object_key: str) -> bytes:
    response = get_minio().get_object(bucket, object_key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


async def get_bytes_async(bucket: str, object_key: str) -> bytes:
    return await asyncio.to_thread(get_bytes, bucket, object_key)


def remove_object(bucket: str, object_key: str) -> None:
    try:
        get_minio().remove_object(bucket, object_key)
    except S3Error:
        pass


async def remove_object_async(bucket: str, object_key: str) -> None:
    await asyncio.to_thread(remove_object, bucket, object_key)
