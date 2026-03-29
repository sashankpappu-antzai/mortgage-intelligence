"""
Cloud-agnostic storage abstraction.
Supports S3 (AWS), GCS (Google Cloud), Azure Blob, and local filesystem.
Configured via STORAGE_PROVIDER environment variable.
"""

import os
from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageProvider(ABC):
    """Abstract storage interface - implement per cloud provider."""

    @abstractmethod
    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Upload file and return the storage key."""
        ...

    @abstractmethod
    async def download(self, key: str) -> bytes:
        """Download file by key."""
        ...

    @abstractmethod
    async def get_presigned_url(self, key: str, expires_in: int = 900) -> str:
        """Generate a pre-signed URL for temporary access (default 15 min)."""
        ...

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete file by key."""
        ...

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if file exists."""
        ...


class S3Storage(StorageProvider):
    """AWS S3 storage provider."""

    def __init__(self, bucket: str, region: str = "us-east-1", endpoint_url: str | None = None):
        import boto3
        self.bucket = bucket
        session_kwargs = {"region_name": region}
        self._client = boto3.client("s3", endpoint_url=endpoint_url, **session_kwargs)

    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return key

    async def download(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()

    async def get_presigned_url(self, key: str, expires_in: int = 900) -> str:
        return self._client.generate_presigned_url(
            "get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=expires_in
        )

    async def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=key)

    async def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
            return True
        except self._client.exceptions.ClientError:
            return False


class GCSStorage(StorageProvider):
    """Google Cloud Storage provider."""

    def __init__(self, bucket: str, project: str | None = None):
        from google.cloud import storage
        self._client = storage.Client(project=project)
        self._bucket = self._client.bucket(bucket)

    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        blob = self._bucket.blob(key)
        blob.upload_from_string(data, content_type=content_type)
        return key

    async def download(self, key: str) -> bytes:
        blob = self._bucket.blob(key)
        return blob.download_as_bytes()

    async def get_presigned_url(self, key: str, expires_in: int = 900) -> str:
        import datetime
        blob = self._bucket.blob(key)
        return blob.generate_signed_url(expiration=datetime.timedelta(seconds=expires_in), method="GET")

    async def delete(self, key: str) -> None:
        blob = self._bucket.blob(key)
        blob.delete()

    async def exists(self, key: str) -> bool:
        blob = self._bucket.blob(key)
        return blob.exists()


class AzureBlobStorage(StorageProvider):
    """Azure Blob Storage provider."""

    def __init__(self, container: str, connection_string: str | None = None):
        from azure.storage.blob import BlobServiceClient
        self._container_name = container
        if connection_string:
            self._client = BlobServiceClient.from_connection_string(connection_string)
        else:
            self._client = BlobServiceClient.from_connection_string(os.environ["AZURE_STORAGE_CONNECTION_STRING"])
        self._container = self._client.get_container_client(container)

    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        blob = self._container.get_blob_client(key)
        blob.upload_blob(data, content_type=content_type, overwrite=True)
        return key

    async def download(self, key: str) -> bytes:
        blob = self._container.get_blob_client(key)
        return blob.download_blob().readall()

    async def get_presigned_url(self, key: str, expires_in: int = 900) -> str:
        from azure.storage.blob import BlobSasPermissions, generate_blob_sas
        from datetime import datetime, timedelta, timezone
        blob = self._container.get_blob_client(key)
        sas = generate_blob_sas(
            account_name=self._client.account_name,
            container_name=self._container_name,
            blob_name=key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        )
        return f"{blob.url}?{sas}"

    async def delete(self, key: str) -> None:
        blob = self._container.get_blob_client(key)
        blob.delete_blob()

    async def exists(self, key: str) -> bool:
        blob = self._container.get_blob_client(key)
        try:
            blob.get_blob_properties()
            return True
        except Exception:
            return False


class LocalStorage(StorageProvider):
    """Local filesystem storage for development."""

    def __init__(self, base_path: str = "./storage"):
        self.base_path = base_path
        os.makedirs(base_path, exist_ok=True)

    async def upload(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        path = os.path.join(self.base_path, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return key

    async def download(self, key: str) -> bytes:
        path = os.path.join(self.base_path, key)
        with open(path, "rb") as f:
            return f.read()

    async def get_presigned_url(self, key: str, expires_in: int = 900) -> str:
        return f"/storage/{key}"

    async def delete(self, key: str) -> None:
        path = os.path.join(self.base_path, key)
        if os.path.exists(path):
            os.remove(path)

    async def exists(self, key: str) -> bool:
        return os.path.exists(os.path.join(self.base_path, key))


def create_storage(provider: str = "local", **kwargs) -> StorageProvider:
    """Factory function to create the configured storage provider."""
    providers = {
        "s3": S3Storage,
        "gcs": GCSStorage,
        "azure": AzureBlobStorage,
        "local": LocalStorage,
    }
    if provider not in providers:
        raise ValueError(f"Unknown storage provider: {provider}. Choose from: {list(providers.keys())}")
    return providers[provider](**kwargs)
