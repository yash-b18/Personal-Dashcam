"""
Cloudflare R2 client — S3-compatible object storage interface.

Wraps boto3 to provide typed, purpose-built methods for listing
dashcam clips, generating presigned URLs for video playback, and
downloading videos to temporary local paths for processing.

Cloudflare R2 is S3-compatible; the endpoint URL is:
    https://{account_id}.r2.cloudflarestorage.com
"""

import logging
import tempfile
from pathlib import Path

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from api.config import Settings, get_settings

logger = logging.getLogger(__name__)


class R2Client:
    """
    Typed interface for Cloudflare R2 object storage.

    All operations are synchronous and safe to call from Celery workers.
    For large listings (1,200+ objects), uses paginated iteration to
    avoid memory issues.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        """
        Initialise the R2 client from application settings.

        Args:
            settings: Optional Settings instance. Defaults to get_settings().
        """
        self._settings = settings or get_settings()
        self._client = boto3.client(
            "s3",
            endpoint_url=self._settings.r2_endpoint_url,
            aws_access_key_id=self._settings.r2_access_key_id,
            aws_secret_access_key=self._settings.r2_secret_access_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )
        self._bucket = self._settings.r2_bucket_name

    # ── Listing ───────────────────────────────────────────────────────

    def list_objects(self, prefix: str) -> list[dict]:
        """
        List all objects under a given prefix, handling pagination.

        Args:
            prefix: R2 key prefix to list (e.g. "dashcam/front/").

        Returns:
            List of object metadata dicts with keys:
              Key, Size, LastModified, ETag
        """
        objects: list[dict] = []
        paginator = self._client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self._bucket, Prefix=prefix)
        for page in pages:
            for obj in page.get("Contents", []):
                if obj["Key"].lower().endswith(".mp4"):
                    objects.append(obj)
        logger.info("Listed %d MP4 objects under prefix '%s'", len(objects), prefix)
        return objects

    def list_front_clips(self) -> list[dict]:
        """Return all MP4 objects in the front camera folder."""
        return self.list_objects(self._settings.r2_front_prefix)

    def list_rear_clips(self) -> list[dict]:
        """Return all MP4 objects in the rear camera folder."""
        return self.list_objects(self._settings.r2_rear_prefix)

    # ── Download ──────────────────────────────────────────────────────

    def download_to_temp(self, key: str) -> Path:
        """
        Download an R2 object to a temporary local file.

        The caller is responsible for deleting the file after use.
        Use `download_context` for automatic cleanup.

        Args:
            key: Full R2 object key.

        Returns:
            Path to the downloaded temporary file (suffix .mp4).

        Raises:
            ClientError: If the object does not exist or download fails.
        """
        suffix = Path(key).suffix or ".mp4"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        try:
            logger.debug("Downloading R2 object: %s", key)
            self._client.download_fileobj(self._bucket, key, tmp)
            tmp.flush()
            logger.debug("Downloaded to %s (%d bytes)", tmp.name, Path(tmp.name).stat().st_size)
            return Path(tmp.name)
        except ClientError as exc:
            Path(tmp.name).unlink(missing_ok=True)
            logger.error("Failed to download %s: %s", key, exc)
            raise
        finally:
            tmp.close()

    # ── Presigned URLs ────────────────────────────────────────────────

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """
        Generate a presigned URL for authenticated video playback.

        Used by the API to serve front/rear video streams to the frontend
        without exposing R2 credentials.

        Args:
            key: Full R2 object key.
            expires_in: URL validity in seconds (default 1 hour).

        Returns:
            HTTPS presigned URL string.
        """
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as exc:
            logger.error("Failed to generate presigned URL for %s: %s", key, exc)
            raise

    # ── Object info ───────────────────────────────────────────────────

    def head_object(self, key: str) -> dict:
        """
        Retrieve metadata for an R2 object without downloading it.

        Args:
            key: Full R2 object key.

        Returns:
            Dict with ContentLength, LastModified, ContentType, etc.
        """
        return self._client.head_object(Bucket=self._bucket, Key=key)

    def object_exists(self, key: str) -> bool:
        """Return True if the object exists in the bucket."""
        try:
            self.head_object(key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise
