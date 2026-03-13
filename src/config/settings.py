"""
src/config/settings.py
======================
Single source of truth for all runtime configuration.

Reads environment variables once at import time and exposes a frozen
``Settings`` dataclass so the rest of the codebase never calls
``os.environ.get`` directly.  Missing *required* variables raise an
``EnvironmentError`` immediately on startup rather than failing silently
during a live request.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default themes catalogue — used when THEMES_LIST env var is not set.
# Both the Azure Function and the Batch Launcher share this list so there
# is never a duplication between containers.
# ---------------------------------------------------------------------------
DEFAULT_THEMES: list[str] = [
    # Expected impulsive / superficial engagement
    "celebrity gossip",
    "funny pranks",
    "daily vlog",
    "influencer apology",
    "gaming drama",
    "viral challenges",
    # Expected informational / analytical engagement
    "science documentary",
    "history explained",
    "video essay",
    "philosophy lecture",
    "personal finance",
    "tech gadget review",
    # Highly polarised / debate topics
    "politics debate",
    "conspiracy theory",
]

# Keep the old name as an alias so importing modules don't break.
THEMES = DEFAULT_THEMES


def _require(name: str) -> str:
    """Return the value of *name* from the environment; raise if missing/empty."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set or is empty. "
            "Check your .env file or container environment configuration."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    """Return the value of *name* from the environment, falling back to *default*."""
    return os.environ.get(name, default).strip() or default


def _parse_themes() -> list[str]:
    """Return the active themes list.

    Reads ``THEMES_LIST`` from the environment as a comma-separated string,
    e.g.::

        THEMES_LIST=celebrity gossip,science documentary,politics debate

    Each entry is stripped of surrounding whitespace and blank entries are
    discarded.  If the variable is absent or resolves to an empty list,
    :data:`DEFAULT_THEMES` is used as the fallback so the pipeline always
    has at least one theme to work with.

    Returns:
        A non-empty list of theme strings.
    """
    raw = os.environ.get("THEMES_LIST", "").strip()
    if raw:
        parsed = [t.strip() for t in raw.split(",") if t.strip()]
        if parsed:
            logger.info("Loaded %d themes from THEMES_LIST env var", len(parsed))
            return parsed
    
    logger.info("THEMES_LIST not found or empty — using %d default themes", len(DEFAULT_THEMES))
    return list(DEFAULT_THEMES)


def _parse_bool(name: str, default: bool) -> bool:
    """Parse a boolean environment variable."""
    value = os.environ.get(name, "").lower().strip()
    if not value:
        return default
    return value in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Immutable bag of all runtime settings.

    Instantiate once per process (or test) via :func:`load_settings`.
    """

    # ── Required ──────────────────────────────────────────────────────────────
    youtube_api_key: str

    # ── Optional — Azure storage (only needed when upload_to_cloud=True) ─────
    azure_storage_connection_string: str
    upload_to_cloud: bool

    # ── Optional — local storage path ────────────────────────────────────────
    data_lake_path: str

    # ── Azure Blob container name ─────────────────────────────────────────────
    blob_container_name: str

    # ── YouTube extraction tuning ─────────────────────────────────────────────
    global_comment_limit: int
    is_short: bool

    # ── Batch-launcher tuning ─────────────────────────────────────────────────
    azure_function_url: str
    total_requests: int
    wait_time_seconds: int

    # ── Shared catalogue ──────────────────────────────────────────────────────
    themes: list[str] = field(default_factory=lambda: list(THEMES))


def load_settings() -> Settings:
    """Read environment variables and return a validated :class:`Settings` object.

    Call this once at module initialisation so startup failures are loud and
    immediate rather than deferred to the first request.
    """
    youtube_api_key = _require("YOUTUBE_API_KEY")
    azure_conn_str = _optional("AZURE_STORAGE_CONNECTION_STRING", "")
    data_lake_path = _optional("DATA_LAKE_PATH", "./local_data_lake")
    blob_container_name = _optional("BLOB_CONTAINER_NAME", "youtube-comments")

    try:
        global_comment_limit = int(_optional("GLOBAL_COMMENT_LIMIT", "10000"))
    except ValueError:
        raise EnvironmentError("GLOBAL_COMMENT_LIMIT must be a positive integer.")

    azure_function_url = _optional(
        "AZURE_FUNCTION_URL",
        "http://localhost:7071/api/extract_youtube_comments",
    )

    try:
        total_requests = int(_optional("TOTAL_REQUESTS", "2"))
    except ValueError:
        raise EnvironmentError("TOTAL_REQUESTS must be a positive integer.")

    try:
        wait_time_seconds = int(_optional("WAIT_TIME_SECONDS", "4"))
    except ValueError:
        raise EnvironmentError("WAIT_TIME_SECONDS must be a positive integer.")

    return Settings(
        youtube_api_key=youtube_api_key,
        azure_storage_connection_string=azure_conn_str,
        upload_to_cloud=_parse_bool("UPLOAD_TO_CLOUD", True),
        data_lake_path=data_lake_path,
        blob_container_name=blob_container_name,
        global_comment_limit=global_comment_limit,
        is_short=_parse_bool("IS_SHORT", True),
        azure_function_url=azure_function_url,
        total_requests=total_requests,
        wait_time_seconds=wait_time_seconds,
        themes=_parse_themes(),
    )
