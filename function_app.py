"""
function_app.py
================
Azure Functions HTTP trigger — thin orchestration handler.

All business logic lives in the ``src/`` package:
  - src.config.settings  → environment configuration
  - src.services.youtube_service → YouTube Data API interaction
  - src.services.storage_service → Azure Blob + local file persistence
  - src.utils.file_naming → deterministic output filename generation

This file's only responsibility is:
  1. Parse and validate the incoming HTTP request.
  2. Wire up the service objects with settings from the environment.
  3. Delegate work and return a structured JSON HTTP response.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import azure.functions as func

from src.config.settings import load_settings
from src.services.youtube_service import YouTubeService
from src.services.storage_service import StorageService
from src.utils.file_naming import generate_filename

# ---------------------------------------------------------------------------
# Structured logger — use module-level logger instead of root logger so that
# Azure Application Insights can filter by component name.
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Load settings once at cold-start.  Missing required vars raise immediately
# rather than failing silently on the first request.
# ---------------------------------------------------------------------------
_settings = load_settings()

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# ---------------------------------------------------------------------------
# Request parameter helpers
# ---------------------------------------------------------------------------

def _get_param(req: func.HttpRequest, name: str) -> Optional[str]:
    """Return *name* from query-string, falling back to the JSON body."""
    value = req.params.get(name)
    if value is not None:
        return value
    try:
        body = req.get_json()
        raw = body.get(name)
        return str(raw) if raw is not None else None
    except (ValueError, AttributeError):
        return None


def _parse_bool(value: Optional[str], default: bool = False) -> bool:
    """Safely coerce a string param to a boolean."""
    if value is None:
        return default
    return str(value).strip().lower() in {"true", "1", "yes"}


def _json_response(body: dict, status_code: int = 200) -> func.HttpResponse:
    """Return a JSON-encoded HTTP response with correct Content-Type."""
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json",
    )


# ---------------------------------------------------------------------------
# HTTP Trigger
# ---------------------------------------------------------------------------

@app.route(route="extract_youtube_comments")
def extract_youtube_comments(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger that extracts YouTube comments and persists them.

    Query-string or JSON body parameters
    -------------------------------------
    video_id : str, optional
        A single YouTube video ID.  When provided, comments are fetched
        directly without a search step.
    theme : str, optional
        Search theme used to find videos when *video_id* is omitted.
    is_short : bool, optional
        Whether to restrict the search to YouTube Shorts.  Default: False.
    upload_to_cloud : bool, optional
        When True, upload the result to Azure Blob Storage.  Default: True.
    """
    logger.info("extract_youtube_comments triggered | method=%s", req.method)

    # ── 1. Parse request parameters ─────────────────────────────────────────
    video_id = _get_param(req, "video_id")
    theme = _get_param(req, "theme")
    is_short = _parse_bool(_get_param(req, "is_short"), default=False)
    upload_to_cloud = _parse_bool(_get_param(req, "upload_to_cloud"), default=True)

    logger.info(
        "Request params | video_id=%s | theme=%s | is_short=%s | upload_to_cloud=%s",
        video_id,
        theme,
        is_short,
        upload_to_cloud,
    )

    # ── 2. Input validation ──────────────────────────────────────────────────
    if not video_id and not theme:
        return _json_response(
            {"error": "Provide at least one of 'video_id' or 'theme'."},
            status_code=400,
        )

    if upload_to_cloud and not _settings.azure_storage_connection_string:
        return _json_response(
            {"error": "AZURE_STORAGE_CONNECTION_STRING is required for cloud uploads."},
            status_code=500,
        )

    # ── 3. Initialise services ───────────────────────────────────────────────
    yt_service = YouTubeService(
        api_key=_settings.youtube_api_key,
        global_limit=_settings.global_comment_limit,
    )
    storage_service = StorageService(
        azure_connection_string=_settings.azure_storage_connection_string,
        data_lake_path=_settings.data_lake_path,
        container_name=_settings.blob_container_name,
    )

    try:
        # ── 4. Resolve video IDs ─────────────────────────────────────────────
        if video_id:
            video_ids = [video_id]
        else:
            video_ids = yt_service.search_videos(
                theme=theme,  # type: ignore[arg-type]
                is_short=is_short,
            )
            if not video_ids:
                return _json_response(
                    {"error": f"No videos found for theme '{theme}'."},
                    status_code=404,
                )

        # ── 5. Extract comments ──────────────────────────────────────────────
        comments = yt_service.fetch_comments(
            video_ids=video_ids,
            theme=theme,
            is_short=is_short,
        )

        # ── 6. Persist results ───────────────────────────────────────────────
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        filename = generate_filename(theme=theme, video_ids=video_ids, timestamp=timestamp)

        if upload_to_cloud:
            save_location = storage_service.save_to_cloud(comments=comments, filename=filename)
        else:
            save_location = storage_service.save_locally(comments=comments, filename=filename)

        # ── 7. Return structured success response ────────────────────────────
        return _json_response(
            {
                "status": "success",
                "comments_extracted": len(comments),
                "videos_processed": len(video_ids),
                "saved_to": save_location,
                "filename": filename,
            }
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("Unhandled error in extract_youtube_comments: %s", exc)
        return _json_response(
            {"error": str(exc)},
            status_code=500,
        )
