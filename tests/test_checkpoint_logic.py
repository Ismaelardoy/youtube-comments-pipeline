import sys
import os
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

# Asegurar que la raíz del proyecto y 'src' sean importables
root_path = Path(__file__).parent.parent
sys.path.append(str(root_path))
if str(root_path / "src") not in sys.path:
    sys.path.append(str(root_path / "src"))

from src.services.youtube_service import YouTubeService

class TestYouTubeServiceIncremental(unittest.TestCase):
    def setUp(self):
        self.service = YouTubeService(api_key="test_key", global_limit=10)
        self.service._client = MagicMock()

    def test_collect_video_comments_with_checkpoint_date(self):
        v_id = "video123"
        checkpoint = {"last_published_at": "2025-01-01T00:00:00Z", "last_comment_id": "old_id"}
        
        # Mock response from YouTube API
        mock_response = {
            "items": [
                {
                    "id": "new_id_1",
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "Fresh comment 1",
                                "publishedAt": "2025-01-02T10:00:00Z",
                                "authorDisplayName": "User 1",
                                "likeCount": 5
                            }
                        }
                    }
                },
                {
                    "id": "old_id", # Should trigger early exit
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "Old comment",
                                "publishedAt": "2025-01-01T00:00:00Z",
                                "authorDisplayName": "User 2",
                                "likeCount": 1
                            }
                        }
                    }
                }
            ]
        }
        
        # Setup mock for _execute_comment_page
        self.service._execute_comment_page = MagicMock(return_value=mock_response)
        
        comments = []
        seen_ids = set()
        
        # Patch the client.commentThreads().list call to check params
        with patch.object(self.service._client.commentThreads(), 'list') as mock_list:
            mock_list.return_value.execute.return_value = mock_response # Not needed if we mock _execute_comment_page but good for completeness
            
            self.service._collect_video_comments(
                v_id=v_id,
                theme="test",
                is_short=True,
                video_published_at="2025-01-01T00:00:00Z",
                comments=comments,
                seen_ids=seen_ids,
                checkpoint=checkpoint
            )
            
            # Verify publishedAfter was passed
            args, kwargs = mock_list.call_args
            self.assertEqual(kwargs["publishedAfter"], "2025-01-01T00:00:00Z")
            self.assertEqual(kwargs["order"], "time")

        # Verify only 1 comment was added (the new one)
        self.assertEqual(len(comments), 1)
        self.assertEqual(comments[0]["comment_id"], "new_id_1")
        
        # Verify checkpoint was updated
        self.assertEqual(checkpoint["last_comment_id"], "new_id_1")
        self.assertEqual(checkpoint["last_published_at"], "2025-01-02T10:00:00Z")

    def test_deduplication_in_session(self):
        v_id = "video456"
        # Mock response with duplicates
        mock_response = {
            "items": [
                {
                    "id": "id1",
                    "snippet": {"topLevelComment": {"snippet": {"textDisplay": "Msg 1", "publishedAt": "2025-01-05T00:00:00Z"}}}
                },
                {
                    "id": "id1", # Duplicate
                    "snippet": {"topLevelComment": {"snippet": {"textDisplay": "Msg 1", "publishedAt": "2025-01-05T00:00:00Z"}}}
                }
            ]
        }
        self.service._execute_comment_page = MagicMock(return_value=mock_response)
        
        comments = []
        seen_ids = set()
        
        self.service._collect_video_comments(
            v_id=v_id,
            theme="test",
            is_short=True,
            video_published_at="2025-01-01T00:00:00Z",
            comments=comments,
            seen_ids=seen_ids,
            checkpoint={}
        )
        
        self.assertEqual(len(comments), 1)
        self.assertEqual(len(seen_ids), 1)

    def test_fetch_comments_updates_checkpoint_dict_for_new_video(self):
        v_id = "new_video_999"
        checkpoints = {} # Empty initial checkpoints
        
        # Mock response
        mock_response = {
            "items": [
                {
                    "id": "new_comment_id",
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "Hello world",
                                "publishedAt": "2025-01-10T12:00:00Z",
                                "authorDisplayName": "Tester",
                                "likeCount": 0
                            }
                        }
                    }
                }
            ]
        }
        self.service._execute_comment_page = MagicMock(return_value=mock_response)
        self.service.get_video_publish_dates = MagicMock(return_value={v_id: "2025-01-01T00:00:00Z"})

        comments = self.service.fetch_comments(
            video_ids=[v_id],
            theme="test",
            is_short=True,
            checkpoints=checkpoints
        )

        # Verify comment was fetched
        self.assertEqual(len(comments), 1)
        
        # CRITICAL: Verify the checkpoints dictionary now contains the entry for this new video
        self.assertIn(v_id, checkpoints)
        self.assertEqual(checkpoints[v_id]["last_comment_id"], "new_comment_id")
        self.assertEqual(checkpoints[v_id]["last_published_at"], "2025-01-10T12:00:00Z")

    def test_search_videos_pagination(self):
        self.service._max_search_results = 10
        
        # Mock first page response
        mock_response_1 = {
            "items": [{"id": {"videoId": "vid1"}}, {"id": {"videoId": "vid2"}}],
            "nextPageToken": "token2"
        }
        # Mock second page response
        mock_response_2 = {
            "items": [{"id": {"videoId": "vid3"}}],
            # No nextPageToken
        }
        
        self.service._execute_search = MagicMock(side_effect=[mock_response_1, mock_response_2])
        
        video_ids = self.service.search_videos(theme="test", is_short=True)
        
        # Should have called _execute_search twice
        self.assertEqual(self.service._execute_search.call_count, 2)
        # Should have collected all 3 IDs
        self.assertEqual(len(video_ids), 3)
        self.assertEqual(video_ids, ["vid1", "vid2", "vid3"])

if __name__ == "__main__":
    unittest.main()
