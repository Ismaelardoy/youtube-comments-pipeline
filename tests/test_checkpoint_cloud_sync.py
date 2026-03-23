"""
tests/test_checkpoint_cloud_sync.py
===================================
Unit-tests for the new Checkpoint Cloud Sync feature.
"""
import unittest
import os
import json
import shutil
from unittest.mock import MagicMock, patch
from pathlib import Path

# Ensure project root is importable
import sys
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.services.checkpoint_service import CheckpointService

class TestCheckpointCloudSync(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("./tmp_test_checkpoints")
        self.test_dir.mkdir(exist_ok=True)
        self.filename = "test_checkpoint.json"
        self.local_path = self.test_dir / self.filename

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_load_from_cloud_when_local_missing(self):
        # Setup: Local file does NOT exist
        mock_storage = MagicMock()
        checkpoint_content = {"vid1": {"last_comment_id": "c1", "last_published_at": "2025"}}
        mock_storage.download_from_cloud.return_value = json.dumps(checkpoint_content)

        svc = CheckpointService(str(self.test_dir), self.filename, storage_service=mock_storage)
        checkpoints = svc.load_checkpoints()

        # Verify: data was downloaded and loaded
        self.assertEqual(checkpoints, checkpoint_content)
        mock_storage.download_from_cloud.assert_called_with(self.filename)
        # Verify: it was also saved locally for next time
        self.assertTrue(self.local_path.exists())

    def test_save_syncs_to_cloud(self):
        mock_storage = MagicMock()
        svc = CheckpointService(str(self.test_dir), self.filename, storage_service=mock_storage)
        
        svc.update_checkpoint("vid2", "c2", "2025-01-01")
        svc.save_checkpoints()

        # Verify: local save happened
        self.assertTrue(self.local_path.exists())
        with open(self.local_path, "r") as f:
            data = json.load(f)
        self.assertIn("vid2", data)

        # Verify: cloud upload happened
        mock_storage.upload_raw.assert_called()
        call_args = mock_storage.upload_raw.call_args
        self.assertIn('"vid2"', call_args[0][0])
        self.assertEqual(call_args[0][1], self.filename)

    def test_no_cloud_sync_when_storage_service_missing(self):
        svc = CheckpointService(str(self.test_dir), self.filename, storage_service=None)
        svc.update_checkpoint("vid3", "c3", "2025-01-02")
        # Should not raise any error even if cloud sync is skipped
        svc.save_checkpoints()
        self.assertTrue(self.local_path.exists())

if __name__ == "__main__":
    unittest.main()
