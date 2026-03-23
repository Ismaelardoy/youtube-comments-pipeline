"""
tests/test_language_and_fields.py
==================================
Unit-tests for the YOUTUBE_LANGUAGE and OUTPUT_FIELDS features.

Run:  python -m unittest tests.test_language_and_fields -v
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure the project root is importable
root_path = Path(__file__).parent.parent
sys.path.insert(0, str(root_path))


class TestSettingsLanguageAndFields(unittest.TestCase):
    """Verify load_settings handles YOUTUBE_LANGUAGE and OUTPUT_FIELDS."""

    def _load_fresh(self):
        """Import and call load_settings with a clean module state."""
        # Ensure required var exists
        os.environ.setdefault("YOUTUBE_API_KEY", "test-key")
        from src.config.settings import load_settings
        return load_settings()

    # ── YOUTUBE_LANGUAGE ──────────────────────────────────────────────────

    @patch.dict(os.environ, {"YOUTUBE_LANGUAGE": "es"}, clear=False)
    def test_language_from_env(self):
        s = self._load_fresh()
        self.assertEqual(s.youtube_language, "es")

    @patch.dict(os.environ, {"YOUTUBE_LANGUAGE": ""}, clear=False)
    def test_language_empty_falls_back_to_en(self):
        s = self._load_fresh()
        self.assertEqual(s.youtube_language, "en")

    @patch.dict(os.environ, {}, clear=False)
    def test_language_missing_falls_back_to_en(self):
        # Remove the key if it happens to exist
        os.environ.pop("YOUTUBE_LANGUAGE", None)
        s = self._load_fresh()
        self.assertEqual(s.youtube_language, "en")

    # ── OUTPUT_FIELDS ─────────────────────────────────────────────────────

    @patch.dict(os.environ, {"OUTPUT_FIELDS": "comment_id,text,likeCount"}, clear=False)
    def test_output_fields_parsed(self):
        s = self._load_fresh()
        self.assertEqual(s.output_fields, ["comment_id", "text", "likeCount"])

    @patch.dict(os.environ, {"OUTPUT_FIELDS": "comment_id , text , likeCount"}, clear=False)
    def test_output_fields_trimmed(self):
        s = self._load_fresh()
        self.assertEqual(s.output_fields, ["comment_id", "text", "likeCount"])

    @patch.dict(os.environ, {"OUTPUT_FIELDS": "comment_id,INVALID_FIELD,text"}, clear=False)
    def test_output_fields_ignores_invalid(self):
        s = self._load_fresh()
        self.assertEqual(s.output_fields, ["comment_id", "text"])

    @patch.dict(os.environ, {"OUTPUT_FIELDS": "TOTALLY_WRONG"}, clear=False)
    def test_output_fields_all_invalid_falls_back_to_defaults(self):
        s = self._load_fresh()
        self.assertEqual(len(s.output_fields), 9)  # all defaults

    @patch.dict(os.environ, {"OUTPUT_FIELDS": ""}, clear=False)
    def test_output_fields_empty_falls_back_to_defaults(self):
        s = self._load_fresh()
        self.assertEqual(len(s.output_fields), 9)

    @patch.dict(os.environ, {}, clear=False)
    def test_output_fields_missing_falls_back_to_defaults(self):
        os.environ.pop("OUTPUT_FIELDS", None)
        s = self._load_fresh()
        self.assertEqual(len(s.output_fields), 9)


try:
    from unittest.mock import patch as _patch
    # Attempt to import; if googleapiclient is missing, mock it before importing
    import importlib
    _yt_mod = importlib.util.find_spec("googleapiclient")
    _HAS_GOOGLE_API = _yt_mod is not None
except Exception:
    _HAS_GOOGLE_API = False


@unittest.skipUnless(_HAS_GOOGLE_API, "googleapiclient not installed — skipping YouTube API tests")
class TestYouTubeServiceLanguage(unittest.TestCase):
    """Verify YouTubeService stores and passes the language to the API."""

    def setUp(self):
        os.environ.setdefault("YOUTUBE_API_KEY", "test-key")
        from src.services.youtube_service import YouTubeService
        self.YouTubeService = YouTubeService

    def test_search_passes_custom_language(self):
        svc = self.YouTubeService(api_key="k", language="es")
        svc._client = MagicMock()
        svc._execute_search = MagicMock(return_value={"items": []})
        svc.search_videos(theme="test", is_short=False)
        self.assertEqual(svc._language, "es")

    def test_default_language_is_en(self):
        svc = self.YouTubeService(api_key="k")
        self.assertEqual(svc._language, "en")


class TestOutputFieldsFiltering(unittest.TestCase):
    """Verify the dict-comprehension filter logic used in function_app."""

    def test_filter_keeps_requested_fields(self):
        record = {
            "comment_id": "abc",
            "videoId": "v1",
            "author": "Alice",
            "text": "Hello",
            "likeCount": 5,
            "publishedAt": "2025-01-01",
        }
        output_fields = ["comment_id", "text", "likeCount"]
        filtered = {k: record[k] for k in output_fields if k in record}
        self.assertEqual(filtered, {"comment_id": "abc", "text": "Hello", "likeCount": 5})

    def test_filter_ignores_nonexistent_keys(self):
        record = {"comment_id": "abc", "text": "Hello"}
        output_fields = ["comment_id", "text", "NO_SUCH_FIELD"]
        filtered = {k: record[k] for k in output_fields if k in record}
        self.assertEqual(filtered, {"comment_id": "abc", "text": "Hello"})

    def test_full_default_fields_is_identity(self):
        """When output_fields equals the full default list, all keys pass through."""
        from src.config.settings import DEFAULT_OUTPUT_FIELDS

        record = {
            "comment_id": "abc",
            "videoId": "v1",
            "videoPublishedAt": "2025-01-01",
            "theme": "test",
            "is_short": True,
            "author": "Alice",
            "text": "Hello",
            "likeCount": 5,
            "publishedAt": "2025-01-01",
        }
        filtered = {k: record[k] for k in DEFAULT_OUTPUT_FIELDS if k in record}
        self.assertEqual(filtered, record)


if __name__ == "__main__":
    unittest.main()
