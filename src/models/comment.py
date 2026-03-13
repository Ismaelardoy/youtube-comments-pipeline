"""
src/models/comment.py
=====================
Typed contract for a single YouTube comment record.

Using ``TypedDict`` keeps the structure purely declarative (no runtime
overhead, JSON-serialisable without extra adapters) while allowing static
type checkers (mypy / pyright) to catch field-name typos anywhere in the
codebase.
"""

from __future__ import annotations

from typing import Optional
from typing_extensions import TypedDict


class CommentRecord(TypedDict):
    """A single cleaned YouTube comment ready for downstream analysis.

    All fields that come from the YouTube API are typed as ``Optional``
    because the API may omit them for certain comment types.
    """

    videoId: str
    """YouTube video ID from which this comment was collected."""

    videoPublishedAt: Optional[str]
    """ISO-8601 timestamp when the **video itself** was published on YouTube.
    Distinct from ``publishedAt``, which is the comment's own date."""

    theme: Optional[str]
    """Search theme used to discover the parent video. ``None`` if the
    video was requested directly by ID."""

    is_short: bool
    """True when the parent video is a YouTube Short."""

    author: Optional[str]
    """Display name of the comment author."""

    text: str
    """Cleaned comment text (HTML tags, URLs, and emojis removed)."""

    likeCount: int
    """Number of likes on the top-level comment thread."""

    publishedAt: Optional[str]
    """ISO-8601 timestamp string from the YouTube API."""
