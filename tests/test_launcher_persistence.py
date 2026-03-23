"""
tests/test_launcher_persistence.py
==================================
Unit-tests for the Batch Launcher's persistent theme queue.
"""
import unittest
import os
import json
import shutil
from pathlib import Path

# Ensure project root is importable
import sys
from unittest.mock import MagicMock
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Mock heavy dependencies before importing batch_launcher
sys.modules["tenacity"] = MagicMock()
sys.modules["requests"] = MagicMock()
# Mock src internal imports
sys.modules["src"] = MagicMock()
sys.modules["src.config"] = MagicMock()
sys.modules["src.config.settings"] = MagicMock()
sys.modules["src.services"] = MagicMock()
sys.modules["src.services.storage_service"] = MagicMock()

# Now we can safely import the internal helpers
from batch_launcher import _load_launcher_state, _save_launcher_state

class TestLauncherPersistence(unittest.TestCase):
    def setUp(self):
        self.test_dir = Path("./tmp_test_launcher")
        self.test_dir.mkdir(exist_ok=True)
        self.state_file = self.test_dir / "launcher_state.json"

    def tearDown(self):
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_save_and_load_state(self):
        themes = ["theme1", "theme2", "theme3"]
        _save_launcher_state(str(self.test_dir), themes)
        
        # Verify file exists
        self.assertTrue(self.state_file.exists())
        
        # Verify loading works
        loaded = _load_launcher_state(str(self.test_dir))
        self.assertEqual(loaded, themes)

    def test_load_non_existent_state(self):
        loaded = _load_launcher_state(str(self.test_dir))
        self.assertEqual(loaded, [])

    def test_load_corrupted_state(self):
        with open(self.state_file, "w") as f:
            f.write("not a json")
        
        loaded = _load_launcher_state(str(self.test_dir))
        self.assertEqual(loaded, [])

    def test_load_from_cloud_when_local_missing(self):
        mock_storage = MagicMock()
        themes = ["cloud1", "cloud2"]
        mock_storage.download_from_cloud.return_value = json.dumps({"remaining_themes": themes})
        
        # Local file DOES NOT exist
        loaded = _load_launcher_state(str(self.test_dir), storage_service=mock_storage)
        
        self.assertEqual(loaded, themes)
        mock_storage.download_from_cloud.assert_called_with("launcher_state.json")

    def test_save_syncs_to_cloud(self):
        mock_storage = MagicMock()
        themes = ["sync1", "sync2"]
        
        _save_launcher_state(str(self.test_dir), themes, storage_service=mock_storage)
        
        # Verify local save
        self.assertTrue(self.state_file.exists())
        # Verify cloud upload
        mock_storage.upload_raw.assert_called()
        call_args = mock_storage.upload_raw.call_args
        self.assertIn('"sync1"', call_args[0][0])

if __name__ == "__main__":
    unittest.main()
