"""
worker.py — conversion execution and webhook dispatch.

Separates the conversion side-effects (webhook notification) from the
converter module, which stays focused on the pandoc invocation.
"""

import logging
from datetime import datetime
from typing import Optional

import requests

from converter import run_conversion
from db import get_db

logger = logging.getLogger(__name__)


def _dispatch_webhook(webhook_url: str, payload: dict) -> None:
    """POST the completion payload to the caller-supplied webhook URL."""
    try:
        resp = requests.post(webhook_url, json=payload, timeout=5)
        resp.raise_for_status()
        logger.info("Webhook delivered to %s (status %s)", webhook_url, resp.status_code)
    except requests.RequestException as exc:
        logger.warning("Webhook delivery failed for %s: %s", webhook_url, exc)


def run_job(
    job_id: str,
    input_path: str,
    output_format: str,
    output_name: str,
    webhook_url: Optional[str] = None,
) -> dict:
    """
    Execute a conversion job and, if a webhook URL was provided, POST the
    result payload to that URL when the job completes (success or failure).

    Returns the raw result dict from run_conversion.
    """
    result = run_conversion(job_id, input_path, output_format, output_name)
    finished = datetime.utcnow().isoformat()

    if result["success"]:
        status_val = "completed"
        error_val = None
    else:
        status_val = "failed"
        error_val = result["stderr"][:1000] if result["stderr"] else "Unknown error"

    with get_db() as db:
        db.execute(
            """UPDATE jobs SET status = ?, output_path = ?, error = ?, finished_at = ?
               WHERE job_id = ?""",
            (status_val, result["output_path"], error_val, finished, job_id),
        )

    if webhook_url:
        payload: dict = {
            "job_id": job_id,
            "status": status_val,
        }
        if result["success"]:
            payload["output_url"] = f"/jobs/{job_id}/download"
        else:
            payload["error"] = error_val

        _dispatch_webhook(webhook_url, payload)

    return {**result, "status": status_val, "error": error_val}
