"""
batch_launcher.py
==================
Orchestrates repeated HTTP calls to the Azure Function extraction endpoint.

All configuration is read from environment variables via
:mod:`src.config.settings`, so there are no hardcoded values in this file.
The themes catalogue is also shared from the same module — no duplication.

Features
--------
- Structured log output (timestamp | level | logger | message).
- Exponential back-off retry on ``ConnectionError`` via :mod:`tenacity`.
- Shuffled, exhaustive theme rotation: every theme is used before repeating.
- Clean summary at the end with success/error counts.
"""

from __future__ import annotations

import logging
import random
import sys
import time

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)

from src.config.settings import load_settings

# ---------------------------------------------------------------------------
# Structured logging setup — consistent format across local runs and Docker.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Retry policy for connection-level failures (network blips, container not
# ready yet, etc.).  Does NOT retry on HTTP 4xx/5xx — those are logged as
# warnings so the batch continues.
# ---------------------------------------------------------------------------
_connection_retry = retry(
    retry=retry_if_exception_type(requests.exceptions.ConnectionError),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, min=3, max=30),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)


@_connection_retry
def _call_function(url: str, payload: dict, timeout: int) -> requests.Response:
    """POST *payload* to *url* and return the response.

    Decorated with :func:`_connection_retry` so transient ``ConnectionError``
    exceptions are retried automatically with exponential back-off.

    Args:
        url: Full URL of the Azure Function endpoint.
        payload: JSON-serialisable dict with extraction parameters.
        timeout: Request timeout in seconds.

    Returns:
        The :class:`requests.Response` object on success.

    Raises:
        requests.exceptions.ConnectionError: After all retries are exhausted.
        requests.exceptions.Timeout: If the server does not respond in time.
    """
    return requests.get(url, json=payload, timeout=timeout)


def _build_shuffled_themes(themes: list[str]) -> list[str]:
    """Return a randomly shuffled copy of *themes*."""
    shuffled = themes.copy()
    random.shuffle(shuffled)
    return shuffled


def start_launcher() -> None:
    """Main entry point — runs the batch extraction loop."""
    settings = load_settings()

    logger.info("=" * 60)
    logger.info("Batch Launcher starting")
    logger.info("Target URL    : %s", settings.azure_function_url)
    logger.info("Total requests: %d", settings.total_requests)
    logger.info("Wait between  : %ds", settings.wait_time_seconds)
    logger.info("=" * 60)

    successes = 0
    errors = 0
    shuffled_themes = _build_shuffled_themes(settings.themes)

    for i in range(1, settings.total_requests + 1):
        # Reshuffle if all themes have been used
        if not shuffled_themes:
            logger.info("All themes exhausted — reshuffling.")
            shuffled_themes = _build_shuffled_themes(settings.themes)

        selected_theme = shuffled_themes.pop()
        payload = {
            "theme": selected_theme,
            "is_short": settings.is_short,
            "upload_to_cloud": settings.upload_to_cloud,
        }

        logger.info(
            "[%d/%d] Sending request | theme=%r",
            i,
            settings.total_requests,
            selected_theme,
        )

        try:
            response = _call_function(
                url=settings.azure_function_url,
                payload=payload,
                timeout=600,  # 10-minute timeout — the function may fetch 10k comments
            )

            if response.status_code == 200:
                body = response.json() if response.content else {}
                logger.info(
                    "[%d/%d] OK | comments=%s | saved_to=%s",
                    i,
                    settings.total_requests,
                    body.get("comments_extracted", "?"),
                    body.get("saved_to", "?"),
                )
                successes += 1
            else:
                logger.warning(
                    "[%d/%d] HTTP %d | response=%s",
                    i,
                    settings.total_requests,
                    response.status_code,
                    response.text[:120],
                )
                errors += 1

        except requests.exceptions.Timeout:
            logger.error(
                "[%d/%d] Timeout — function took longer than 10 minutes.",
                i,
                settings.total_requests,
            )
            errors += 1

        except requests.exceptions.ConnectionError as exc:
            # This is raised only after all tenacity retries are exhausted.
            logger.error(
                "[%d/%d] Connection failed after retries: %s",
                i,
                settings.total_requests,
                exc,
            )
            errors += 1

        except Exception as exc:  # noqa: BLE001
            logger.error(
                "[%d/%d] Unexpected error: %s",
                i,
                settings.total_requests,
                exc,
            )
            errors += 1

        finally:
            if i < settings.total_requests:
                logger.info("Waiting %ds before next request…", settings.wait_time_seconds)
                time.sleep(settings.wait_time_seconds)

    # ── Summary ──────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info(
        "Batch complete | successes=%d | errors=%d | total=%d",
        successes,
        errors,
        settings.total_requests,
    )
    logger.info("=" * 60)


if __name__ == "__main__":
    start_launcher()
