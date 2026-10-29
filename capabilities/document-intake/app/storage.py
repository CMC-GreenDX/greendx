"""Object storage on SeaweedFS through its S3 API. Each tenant has its own bucket: ecotrace-<tenant_id>."""

from __future__ import annotations

import asyncio
import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://seaweedfs:8333")
BUCKET_PREFIX = os.environ.get("S3_BUCKET_PREFIX", "ecotrace-")

_s3 = boto3.client(
    "s3",
    endpoint_url=S3_ENDPOINT,
    aws_access_key_id=os.environ.get("S3_ACCESS_KEY", ""),
    aws_secret_access_key=os.environ.get("S3_SECRET_KEY", ""),
    region_name="us-east-1",
    config=Config(s3={"addressing_style": "path"}, retries={"max_attempts": 3}),
)
_known_buckets: set[str] = set()


def bucket_for(tenant_id: str) -> str:
    return f"{BUCKET_PREFIX}{tenant_id}"


def _ensure_bucket(bucket: str) -> None:
    # Phase 2: dxctl creates the bucket at onboarding. Until then it is created on first use.
    if bucket in _known_buckets:
        return
    try:
        _s3.head_bucket(Bucket=bucket)
    except ClientError:
        _s3.create_bucket(Bucket=bucket)
    _known_buckets.add(bucket)


def _put(tenant_id: str, key: str, content: bytes, content_type: str) -> str:
    bucket = bucket_for(tenant_id)
    _ensure_bucket(bucket)
    _s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)
    return f"s3://{bucket}/{key}"


def _get(tenant_id: str, uri: str) -> bytes:
    bucket, _, key = uri.removeprefix("s3://").partition("/")
    if bucket != bucket_for(tenant_id):  # never read another tenant's bucket, whatever the database says
        raise PermissionError(uri)
    return _s3.get_object(Bucket=bucket, Key=key)["Body"].read()


async def put(tenant_id: str, key: str, content: bytes, content_type: str) -> str:
    return await asyncio.to_thread(_put, tenant_id, key, content, content_type)


async def get(tenant_id: str, uri: str) -> bytes:
    return await asyncio.to_thread(_get, tenant_id, uri)
