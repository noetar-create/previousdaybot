from __future__ import annotations
import csv
import io
import logging
from datetime import datetime
from typing import Any

import httpx

from .settings import settings

log = logging.getLogger(__name__)


class TradeLogger:
    def __init__(self) -> None:
        self._rows: list[dict[str, Any]] = []

    def append_row(self, **kwargs: Any) -> None:
        kwargs.setdefault("ts", datetime.utcnow().isoformat())
        self._rows.append(kwargs)
        log.info("trade_logged: %s", kwargs)

    async def commit_to_github(self) -> bool:
        cfg = settings()
        if not cfg.github_token or not cfg.github_repo:
            log.warning("github_not_configured — skipping log commit")
            return False
        if not self._rows:
            log.info("no_rows_to_commit")
            return True

        buf = io.StringIO()
        fieldnames = list(self._rows[0].keys())
        writer = csv.DictWriter(buf, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(self._rows)
        csv_content = buf.getvalue()

        api_url = f"https://api.github.com/repos/{cfg.github_repo}/contents/{cfg.github_log_path}"
        headers = {
            "Authorization": f"Bearer {cfg.github_token}",
            "Accept": "application/vnd.github+json",
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                # Check if file exists to get its SHA (required for updates)
                existing_sha: str | None = None
                resp = await client.get(api_url, headers=headers)
                if resp.status_code == 200:
                    existing_sha = resp.json().get("sha")

                import base64
                payload: dict[str, Any] = {
                    "message": f"trade log {datetime.utcnow().date()}",
                    "content": base64.b64encode(csv_content.encode()).decode(),
                }
                if existing_sha:
                    payload["sha"] = existing_sha

                put_resp = await client.put(api_url, headers=headers, json=payload)
                if put_resp.status_code in (200, 201):
                    log.info("github_commit_ok: %d rows", len(self._rows))
                    self._rows.clear()
                    return True
                log.warning("github_commit_failed: %s", put_resp.text[:200])
                return False
        except Exception as exc:
            log.warning("github_commit_error: %s", exc)
            return False


trade_log = TradeLogger()
