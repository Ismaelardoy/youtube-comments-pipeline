"""
src/services/storage_service.py
================================
Encapsulates all persistence operations for extracted comment data.

Responsibilities (Single Responsibility Principle):
- Serialise comment lists to JSON.
- Upload JSON blobs to Azure Blob Storage (cloud path).
- Write JSON files to a configurable local directory (local path).

The local directory path is **never hardcoded** — it is always read from
the ``DATA_LAKE_PATH`` environment variable via :class:`~src.config.settings.Settings`.

This module has **no dependency** on Azure Functions or the YouTube API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Sequence, Optional

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from src.models.comment import CommentRecord

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry policy for Azure Storage operations
# ---------------------------------------------------------------------------
_azure_retry = retry(
    retry=retry_if_exception_type(AzureError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class StorageService:
    """Handles cloud and local persistence of extracted comment records.

    Args:
        azure_connection_string: Azure Storage connection string.  May be
            empty when only local output is needed.
        data_lake_path: Local filesystem directory for JSON output files.
            Created automatically if it does not exist.
        container_name: Azure Blob Storage container name.
    """

    _JSON_INDENT = 4

    def __init__(
        self,
        azure_connection_string: str,
        data_lake_path: str,
        container_name: str = "youtube-comments",
    ) -> None:
        self._azure_connection_string = azure_connection_string
        self._data_lake_path = data_lake_path
        self._container_name = container_name
        logger.info(
            "StorageService initialised | container=%s | local_path=%s",
            container_name,
            data_lake_path,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save_to_cloud(
        self,
        comments: Sequence[CommentRecord],
        filename: str,
    ) -> str:
        """Serialise *comments* to JSON and upload to Azure Blob Storage.

        Args:
            comments: Sequence of comment records to persist.
            filename: Target blob name inside the configured container.

        Returns:
            A human-readable success message with the blob path.

        Raises:
            EnvironmentError: If the Azure connection string is not configured.
            AzureError: If the upload fails after all retry attempts.
        """
        if not self._azure_connection_string:
            raise EnvironmentError(
                "AZURE_STORAGE_CONNECTION_STRING is required for cloud uploads "
                "but is not set."
            )

        json_data = self._serialise(comments)
        self._upload_blob(data=json_data, filename=filename)

        path = f"{self._container_name}/{filename}"
        logger.info("Saved to Azure Blob Storage | blob=%s | records=%d", path, len(comments))
        return f"Azure Blob Storage as '{path}'"

    def upload_raw(self, data: str, filename: str) -> None:
        """Upload any string *data* to Azure Blob Storage as *filename*."""
        if not self._azure_connection_string:
            raise EnvironmentError("AZURE_STORAGE_CONNECTION_STRING not set.")
        self._upload_blob(data=data, filename=filename)

    def download_from_cloud(self, filename: str) -> Optional[str]:
        """Download a blob as a UTF-8 string. Returns None if not found."""
        if not self._azure_connection_string:
            return None
        return self._download_blob(filename)

    def save_locally(
        self,
        comments: Sequence[CommentRecord],
        filename: str,
    ) -> str:
        """Serialise *comments* to JSON and write to the local data-lake directory.

        The directory is created on demand (``exist_ok=True``) so the
        container does not need the path to pre-exist.

        Args:
            comments: Sequence of comment records to persist.
            filename: Output file name (not a full path).

        Returns:
            A human-readable success message with the absolute file path.
        """
        os.makedirs(self._data_lake_path, exist_ok=True)
        file_path = os.path.join(self._data_lake_path, filename)

        json_data = self._serialise(comments)
        with open(file_path, "w", encoding="utf-8") as fh:
            fh.write(json_data)

        logger.info(
            "Saved locally | path=%s | records=%d",
            file_path,
            len(comments),
        )
        return f"local file '{file_path}'"

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _serialise(self, comments: Sequence[CommentRecord]) -> str:
        """Return a JSON string for *comments* with consistent formatting."""
        return json.dumps(list(comments), ensure_ascii=False, indent=self._JSON_INDENT)

    @_azure_retry
    def _upload_blob(self, data: str, filename: str) -> None:
        """Upload *data* as a blob, creating the container if absent."""
        blob_service_client = BlobServiceClient.from_connection_string(
            self._azure_connection_string
        )
        container_client = blob_service_client.get_container_client(self._container_name)

        if not container_client.exists():
            container_client.create_container()
            logger.info("Created Azure Blob container: %s", self._container_name)

        blob_client = blob_service_client.get_blob_client(
            container=self._container_name, blob=filename
        )
        blob_client.upload_blob(data, overwrite=True)

    @_azure_retry
    def _download_blob(self, filename: str) -> Optional[str]:
        """Download a blob, returning None if the container/blob is missing."""
        blob_service_client = BlobServiceClient.from_connection_string(
            self._azure_connection_string
        )
        container_client = blob_service_client.get_container_client(self._container_name)
        if not container_client.exists():
            return None

        blob_client = container_client.get_blob_client(filename)
        if not blob_client.exists():
            return None

        return blob_client.download_blob().readall().decode("utf-8")
