"""
src/services/checkpoint_service.py
==================================
Manages the persistent state (checkpoints) for incremental extraction.

Stored as a JSON file mapping video_id -> {last_comment_id, last_published_at}.
"""

from __future__ import annotations

import json
import logging
import os
from typing import TypedDict, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.storage_service import StorageService

logger = logging.getLogger(__name__)

class VideoCheckpoint(TypedDict):
    last_comment_id: str
    last_published_at: str

class CheckpointService:
    """Handles loading, updating, and saving extraction checkpoints.
    
    Args:
        data_lake_path: Directory where the checkpoint file is stored.
        filename: Name of the checkpoint JSON file.
    """
    
    def __init__(self, data_lake_path: str, filename: str = "checkpoint.json", storage_service: Optional[StorageService] = None) -> None:
        self._checkpoint_path = os.path.join(data_lake_path, filename)
        self._filename = filename
        self._storage_service = storage_service
        self._checkpoints: Dict[str, VideoCheckpoint] = {}
        logger.info("CheckpointService initialised | path=%s | cloud_sync=%s", 
                    self._checkpoint_path, storage_service is not None)

    def load_checkpoints(self) -> Dict[str, VideoCheckpoint]:
        """Load checkpoints from the local filesystem or cloud if missing."""
        # 1. Try local filesystem first
        if os.path.exists(self._checkpoint_path):
            try:
                with open(self._checkpoint_path, "r", encoding="utf-8") as fh:
                    self._checkpoints = json.load(fh)
                logger.info("Loaded %d checkpoint(s) from local file %s", len(self._checkpoints), self._checkpoint_path)
                return self._checkpoints
            except Exception as exc:
                logger.warning("Failed to load local checkpoints: %s", exc)

        # 2. If local fails or is missing, try downloading from cloud
        if self._storage_service:
            logger.info("Local checkpoint missing. Attempting cloud download: %s", self._filename)
            try:
                cloud_data = self._storage_service.download_from_cloud(self._filename)
                if cloud_data:
                    self._checkpoints = json.loads(cloud_data)
                    logger.info("Successfully recovered %d checkpoint(s) from cloud", len(self._checkpoints))
                    # Optimistically save locally for next time
                    self._save_local()
                    return self._checkpoints
                logger.info("No checkpoint found in cloud storage.")
            except Exception as exc:
                logger.warning("Failed to recover checkpoints from cloud: %s", exc)

        logger.info("Starting fresh (no local or cloud checkpoint found).")
        self._checkpoints = {}
        return self._checkpoints

    def get_checkpoint(self, video_id: str) -> Optional[VideoCheckpoint]:
        """Get the checkpoint for a specific video ID."""
        return self._checkpoints.get(video_id)

    def update_checkpoint(self, video_id: str, last_comment_id: str, last_published_at: str) -> None:
        """Update the in-memory checkpoint for a video."""
        self._checkpoints[video_id] = {  # type: ignore[reportGeneralTypeIssues]
            "last_comment_id": last_comment_id,
            "last_published_at": last_published_at
        }

    def save_checkpoints(self) -> None:
        """Save the current in-memory checkpoints to local filesystem and cloud."""
        # 1. Always save locally
        self._save_local()

        # 2. Sync to cloud if available
        if self._storage_service:
            try:
                with open(self._checkpoint_path, "r", encoding="utf-8") as fh:
                    data = fh.read()
                self._storage_service.upload_raw(data, self._filename)
                logger.info("Checkpoint synced to cloud: %s", self._filename)
            except Exception as exc:
                logger.error("Failed to sync checkpoint to cloud: %s", exc)

    def _save_local(self) -> None:
        """Helper to write in-memory state to the local JSON file."""
        os.makedirs(os.path.dirname(self._checkpoint_path), exist_ok=True)
        try:
            with open(self._checkpoint_path, "w", encoding="utf-8") as fh:
                json.dump(self._checkpoints, fh, indent=4, ensure_ascii=False)
            logger.info("Local checkpoint saved: %s", self._checkpoint_path)
        except Exception as exc:
            logger.error("Failed to save local checkpoint: %s", exc)
