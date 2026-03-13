"""
src/utils/file_naming.py
========================
Deterministic, URL-safe filename generators for output JSON blobs.

Keeping all naming logic in one place guarantees that the Azure Function
and any future CLI tools produce identical filenames given the same inputs,
which matters for idempotency checks downstream.
"""

from __future__ import annotations

import re
from typing import Sequence


def _sanitise(value: str) -> str:
    """Replace any non-alphanumeric character with an underscore."""
    return re.sub(r"[^a-zA-Z0-9]", "_", value)


def generate_filename(
    theme: str | None,
    video_ids: Sequence[str],
    timestamp: str,
) -> str:
    """Return a consistent JSON filename for a batch of extracted comments.

    Strategy:
    - If more than one video was processed (search mode), produce a
      ``megablob_<theme>_<timestamp>.json`` name.
    - If exactly one video ID was used (direct mode), produce a
      ``comments_<video_id>_<timestamp>.json`` name.

    Args:
        theme: The search theme string, or ``None`` if a direct video ID
            was used.
        video_ids: Sequence of YouTube video IDs that were processed.
        timestamp: A pre-formatted timestamp string (e.g. ``'20250101120000'``).

    Returns:
        A filesystem- and blob-safe filename string ending in ``.json``.
    """
    if len(video_ids) > 1:
        safe_theme = _sanitise(theme or "random")
        return f"megablob_{safe_theme}_{timestamp}.json"
    return f"comments_{video_ids[0]}_{timestamp}.json"
