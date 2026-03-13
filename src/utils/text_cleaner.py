"""
src/utils/text_cleaner.py
=========================
Pure functions for cleaning raw YouTube comment text.

All transformations are stateless and side-effect-free so they can be
tested in isolation and reused across the function app and the launcher
without any import of Azure or Google libraries.
"""

from __future__ import annotations

import html
import re

import emoji


def clean_comment_text(text: str) -> str:
    """Return a cleaned version of a raw YouTube comment string.

    The pipeline applied in order:

    1. **HTML entity unescaping** — ``&#39;`` → ``'``, ``&amp;`` → ``&``, etc.
    2. **HTML tag removal** — strips ``<br>``, ``<a href=…>``, etc.
    3. **URL removal** — removes ``http://`` and ``https://`` URLs.
    4. **Emoji removal** — uses the ``emoji`` library for full Unicode coverage.
    5. **Whitespace normalisation** — collapses runs of spaces/newlines to a
       single space and strips leading/trailing whitespace.

    Args:
        text: Raw comment text as returned by the YouTube Data API v3.

    Returns:
        Cleaned text, or an empty string if *text* is falsy or becomes
        empty after cleaning.
    """
    if not text:
        return ""

    # 1. Unescape HTML entities (e.g. &#39; → ')
    text = html.unescape(text)

    # 2. Remove all HTML tags (e.g. <br>, <a href="…">…</a>)
    text = re.sub(r"<[^>]+>", " ", text)

    # 3. Remove raw URL strings completely
    text = re.sub(r"https?://\S+", "", text)

    # 4. Remove emojis using the emoji library for full Unicode coverage
    text = emoji.replace_emoji(text, replace="")

    # 5. Collapse excess whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text


def is_meaningful(text: str, min_chars: int = 3) -> bool:
    """Return True if *text* has at least *min_chars* non-whitespace characters.

    Used to filter out comments that are empty or trivially short after
    cleaning (e.g. a single emoji that was stripped, leaving nothing).

    Args:
        text: Cleaned comment text.
        min_chars: Minimum number of characters required to consider the
            text meaningful.  Defaults to 3.

    Returns:
        True if the text meets the minimum length requirement.
    """
    return len(text.strip()) >= min_chars
