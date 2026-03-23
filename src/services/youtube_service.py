"""
src/services/youtube_service.py
================================
Encapsulates all interaction with the YouTube Data API v3.

Responsibilities (Single Responsibility Principle):
- Build and own the authenticated API client.
- Search for video IDs matching a theme.
- Fetch and paginate comment threads for a list of video IDs.
- Apply retry logic (exponential back-off) for transient API errors.

This module has **no dependency** on Azure Functions, Azure Storage, or any
HTTP framework — it is a pure domain service.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta
from typing import Optional

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from src.models.comment import CommentRecord
from src.utils.text_cleaner import clean_comment_text, is_meaningful

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Retry policy — applied to calls that hit the YouTube Data API.
# Retries up to 3 times with exponential back-off (2 s → 4 s → 8 s) for
# transient HTTP errors (429 quota, 500/503 server errors).
# ---------------------------------------------------------------------------
_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def _is_retryable_http_error(exc: BaseException) -> bool:
    return isinstance(exc, HttpError) and exc.resp.status in _RETRYABLE_STATUS_CODES


_youtube_retry = retry(
    retry=retry_if_exception_type(HttpError) | retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=16),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


class YouTubeService:
    """High-level wrapper around the YouTube Data API v3 client.

    Args:
        api_key: YouTube Data API v3 developer key.
        global_limit: Maximum total number of comments to collect across
            all videos in a single run.
    """

    _SEARCH_PUBLISHED_AFTER_START = datetime(2025, 1, 1)
    _MAX_SEARCH_RESULTS = 50
    _MAX_COMMENTS_PER_PAGE = 100

    def __init__(
        self,
        api_key: str,
        global_limit: int = 10_000,
        max_search_results: int = 50,
        language: str = "en",
    ) -> None:
        self._api_key = api_key
        self._global_limit = global_limit
        self._max_search_results = max_search_results
        self._language = language
        self._client = build("youtube", "v3", developerKey=api_key)
        logger.info(
            "YouTubeService initialised | global_limit=%d | language=%s",
            global_limit,
            language,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def search_videos(
        self,
        theme: str,
        is_short: bool,
        published_after: Optional[str] = None,
        published_before: Optional[str] = None,
    ) -> list[str]:
        """Search YouTube for videos matching *theme* and return their IDs.

        Args:
            theme: Free-text search query (e.g. ``"science documentary"``).
            is_short: When True, appends ``#shorts`` to the query and
                restricts ``videoDuration`` to ``"short"``.
            published_after: ISO-8601 timestamp lower-bound for the search
                window.  If omitted, a random date since 2025-01-01 is
                chosen to maximise diversity across runs.

        Returns:
            A list of YouTube video ID strings.  Empty if no videos are
            found.

        Raises:
            HttpError: If the API returns a non-retryable error.
        """
        if published_after is None:
            published_after = self._random_published_after()
        else:
            published_after = self._ensure_rfc3339(published_after)

        if published_before:
            published_before = self._ensure_rfc3339(published_before)

        search_query = f"{theme} #shorts" if is_short else theme
        video_duration = "short" if is_short else "long"

        logger.info(
            "Searching YouTube | query=%r | duration=%s | range=[%s, %s]",
            search_query,
            video_duration,
            published_after,
            published_before or "now",
        )

        video_ids: list[str] = []
        next_page_token: Optional[str] = None

        while len(video_ids) < self._max_search_results:
            response = self._execute_search(
                q=search_query,
                video_duration=video_duration,
                published_after=published_after,
                published_before=published_before,
                page_token=next_page_token,
            )

            items = response.get("items", [])
            page_ids = [item["id"]["videoId"] for item in items]
            video_ids.extend(page_ids)
            
            logger.info("Search page returned %d video(s) | accumulated=%d", len(page_ids), len(video_ids))
            
            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        # Trim to exact requested limit
        video_ids = video_ids[:self._max_search_results]
        logger.info("Search complete | total=%d video(s)", len(video_ids))
        return video_ids

    def get_video_publish_dates(self, video_ids: list[str]) -> dict[str, Optional[str]]:
        """Return a mapping of video ID → ISO-8601 publication date string.

        Calls the ``videos.list`` endpoint in batches of up to 50 IDs
        (the API maximum) to minimise quota consumption.  Videos not
        returned by the API (deleted, private, etc.) map to ``None``.

        Args:
            video_ids: List of YouTube video IDs to look up.

        Returns:
            Dict mapping each ``video_id`` to its ``publishedAt`` string,
            or ``None`` if unavailable.
        """
        dates: dict[str, Optional[str]] = {v_id: None for v_id in video_ids}
        batch_size = 50  # API maximum per call
        ids_seq = list(video_ids)  # local copy; Sequence[str] for safe slicing

        for start in range(0, len(ids_seq), batch_size):
            batch = ids_seq[start : start + batch_size]
            response = self._execute_videos_list(ids=batch)
            for item in response.get("items", []):
                v_id = item["id"]
                dates[v_id] = item.get("snippet", {}).get("publishedAt")

        logger.info(
            "Fetched publish dates for %d video(s)",
            sum(1 for v in dates.values() if v is not None),
        )
        return dates

    def fetch_comments(
        self,
        video_ids: list[str],
        theme: Optional[str],
        is_short: bool,
        video_publish_dates: Optional[dict[str, Optional[str]]] = None,
        checkpoints: Optional[dict[str, dict]] = None,
    ) -> list[CommentRecord]:
        """Fetch cleaned top-level comments from a list of YouTube video IDs.

        Paginates through all available comment pages for each video until
        ``global_limit`` is reached.  Videos that have comments disabled or
        return an API error are skipped with a warning log instead of
        aborting the entire batch.

        Args:
            video_ids: List of YouTube video IDs to process.
            theme: The search theme used to discover these videos, or
                ``None`` if the video IDs were provided directly.
            is_short: Whether the videos are YouTube Shorts.
            video_publish_dates: Optional pre-fetched mapping of video ID to
                publication date.  When ``None``, dates are fetched
                automatically via :meth:`get_video_publish_dates`.
            checkpoints: Optional dictionary of checkpoints per video ID.
                Used to skip already processed comments and save quota.

        Returns:
            A list of :class:`~src.models.comment.CommentRecord` dicts,
            each representing one cleaned comment.
        """
        if video_publish_dates is None:
            video_publish_dates = self.get_video_publish_dates(video_ids)

        comments: list[CommentRecord] = []
        seen_ids: set[str] = set()

        for v_id in video_ids:
            if len(comments) >= self._global_limit:
                logger.info("Global comment limit (%d) reached — stopping.", self._global_limit)
                break

            logger.info(
                "Fetching comments | video_id=%s | accumulated=%d",
                v_id,
                len(comments),
            )
            try:
                self._collect_video_comments(
                    v_id=v_id,
                    theme=theme,
                    is_short=is_short,
                    video_published_at=video_publish_dates.get(v_id),
                    comments=comments,
                    seen_ids=seen_ids,
                    checkpoint=checkpoints.setdefault(v_id, {}) if checkpoints is not None else None,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Skipping video %s due to error: %s",
                    v_id,
                    exc,
                )
                continue

        logger.info("Comment extraction complete | total=%d", len(comments))
        return comments

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @_youtube_retry
    def _execute_search(
        self,
        q: str,
        video_duration: str,
        published_after: str,
        published_before: Optional[str] = None,
        page_token: Optional[str] = None,
    ) -> dict:
        """Execute a YouTube search.list call with retry logic."""
        params = {
            "part": "snippet",
            "q": q,
            "type": "video",
            "videoDuration": video_duration,
            "relevanceLanguage": self._language,
            "publishedAfter": published_after,
            "maxResults": min(50, self._max_search_results), # API maximum per page
        }
        if published_before:
            params["publishedBefore"] = published_before
        if page_token:
            params["pageToken"] = page_token

        request = self._client.search().list(**params)
        return request.execute()

    def _collect_video_comments(
        self,
        v_id: str,
        theme: Optional[str],
        is_short: bool,
        video_published_at: Optional[str],
        comments: list[CommentRecord],
        seen_ids: set[str],
        checkpoint: Optional[dict] = None,
    ) -> None:
        """Paginate through a single video's comment threads, appending to *comments* in-place."""
        last_comment_id = checkpoint.get("last_comment_id") if checkpoint else None
        last_published_at = checkpoint.get("last_published_at") if checkpoint else None

        params = {
            "part": "snippet",
            "videoId": v_id,
            "maxResults": self._MAX_COMMENTS_PER_PAGE,
            "order": "time",  # Ensure we get the most recent first for incremental logic
        }

        # If we have a checkpoint with a date, use it to filter the API request
        # NOTE: YouTube API publishedAfter is exclusive, so it might skip some comments 
        # that arrived at the exact same time. It's safer for quota but might miss edge cases.
        if last_published_at:
            params["publishedAfter"] = last_published_at

        request = self._client.commentThreads().list(**params)
        
        skipped_count = 0
        new_last_comment_id = None
        new_last_published_at = None

        while request is not None and len(comments) < self._global_limit:
            response = self._execute_comment_page(request)

            items = response.get("items", [])
            for item in items:
                if len(comments) >= self._global_limit:
                    break

                comment_id = item["id"]
                snippet = item["snippet"]["topLevelComment"]["snippet"]
                published_at = snippet.get("publishedAt")

                # Early exit if we hit the last seen comment ID or an older date
                if comment_id == last_comment_id or (last_published_at and published_at and published_at <= last_published_at):
                    logger.info("Reached existing comments for video %s — stopping pagination.", v_id)
                    request = None # Break outer loop
                    break

                # In-memory deduplication for the current session
                if comment_id in seen_ids:
                    skipped_count += 1
                    continue

                raw_text: str = snippet.get("textDisplay", "")
                cleaned_text = clean_comment_text(raw_text)

                if not is_meaningful(cleaned_text):
                    continue

                record: CommentRecord = {
                    "comment_id": comment_id,
                    "videoId": v_id,
                    "videoPublishedAt": video_published_at,
                    "theme": theme,
                    "is_short": is_short,
                    "author": snippet.get("authorDisplayName"),
                    "text": cleaned_text,
                    "likeCount": int(snippet.get("likeCount", 0)),
                    "publishedAt": published_at,
                }
                comments.append(record)
                seen_ids.add(comment_id)
                
                # Update high-water marks for checkpointing
                if not new_last_comment_id:
                    new_last_comment_id = comment_id
                if not new_last_published_at or (published_at and published_at > new_last_published_at):
                    new_last_published_at = published_at

            if request is None: # Early exit was triggered
                break

            # Pagination
            if "nextPageToken" in response and len(comments) < self._global_limit:
                request = self._client.commentThreads().list_next(
                    previous_request=request,
                    previous_response=response,
                )
            else:
                break
        
        if skipped_count > 0:
            logger.info("Saltando %d comentarios ya existentes para el vídeo %s", skipped_count, v_id)

        # Update checkpoint in the passed dictionary if applicable
        if checkpoint is not None and new_last_comment_id:
            checkpoint["last_comment_id"] = new_last_comment_id
            checkpoint["last_published_at"] = new_last_published_at
        elif checkpoint is None and new_last_comment_id:
            # If no checkpoint was passed, we might still want to track it somewhere?
            # For now, we rely on the caller passing a dict to be updated.
            pass

    @_youtube_retry
    def _execute_comment_page(self, request) -> dict:  # type: ignore[return]
        """Execute a single commentThreads page request with retry logic."""
        return request.execute()

    @_youtube_retry
    def _execute_videos_list(self, ids: list[str]) -> dict:
        """Call videos.list to retrieve snippet data for up to 50 video IDs."""
        return (
            self._client.videos()
            .list(part="snippet", id=",".join(ids))
            .execute()
        )

    @classmethod
    def _ensure_rfc3339(cls, date_str: str) -> str:
        """Ensure the date string is RFC 3339 compliant for the YouTube API.
        
        If only a date (YYYY-MM-DD) is provided, appends T00:00:00Z.
        """
        date_str = date_str.strip()
        if len(date_str) == 10 and "-" in date_str and "T" not in date_str:
            return f"{date_str}T00:00:00Z"
        return date_str

    @classmethod
    def _random_published_after(cls) -> str:
        """Generate a random ISO-8601 date between 2025-01-01 and today."""
        start = cls._SEARCH_PUBLISHED_AFTER_START
        end = datetime.utcnow()
        delta = end - start
        days = max(1, delta.days)
        random_offset = random.randrange(days)
        dt = start + timedelta(days=random_offset)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
