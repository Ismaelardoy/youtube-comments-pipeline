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
from typing import TypedDict, Dict, Optional

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
    
    def __init__(self, data_lake_path: str, filename: str = "checkpoint.json") -> None:
        self._checkpoint_path = os.path.join(data_lake_path, filename)
        self._checkpoints: Dict[str, VideoCheckpoint] = {}
        logger.info("CheckpointService initialised | path=%s", self._checkpoint_path)

    def load_checkpoints(self) -> Dict[str, VideoCheckpoint]:
        """Load checkpoints from the local filesystem."""
        if not os.path.exists(self._checkpoint_path):
            logger.info("No checkpoint file found at %s. Starting fresh.", self._checkpoint_path)
            self._checkpoints = {}
            return self._checkpoints

        try:
            with open(self._checkpoint_path, "r", encoding="utf-8") as fh:
                self._checkpoints = json.load(fh)
            logger.info("Loaded %d checkpoint(s) from %s", len(self._checkpoints), self._checkpoint_path)
        except Exception as exc:
            logger.warning("Failed to load checkpoints from %s: %s. Starting fresh.", self._checkpoint_path, exc)
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
        """Save the current in-memory checkpoints to the local filesystem."""
        os.makedirs(os.path.dirname(self._checkpoint_path), exist_ok=True)
        try:
            with open(self._checkpoint_path, "w", encoding="utf-8") as fh:
                json.dump(self._checkpoints, fh, indent=4, ensure_ascii=False)
            logger.info("Saved %d checkpoint(s) to %s", len(self._checkpoints), self._checkpoint_path)
        except Exception as exc:
            logger.error("Failed to save checkpoints to %s: %s", self._checkpoint_path, exc)
