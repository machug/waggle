"""Webhook notification dispatcher.

Polls alerts with notified_at IS NULL and severity in (critical, high),
sends JSON payloads to configured webhook URLs with HMAC-SHA256 signatures,
and marks alerts as notified regardless of delivery outcome.
"""

import hashlib
import hmac
import json
import time

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Alert, Hive
from waggle.utils.timestamps import utc_now


def _build_payload(alert: Alert, hive_name: str | None) -> dict:
    """Build webhook payload from alert."""
    return {
        "alert_id": alert.id,
        "type": alert.type,
        "severity": alert.severity,
        "hive_id": alert.hive_id,
        "hive_name": hive_name,
        "message": alert.message,
        "observed_at": alert.observed_at,
        "created_at": alert.created_at,
        "details": json.loads(alert.details_json) if alert.details_json else None,
    }


def _sign_payload(secret: str, timestamp: str, body_bytes: bytes) -> str:
    """Compute HMAC-SHA256 signature over 'timestamp.body'."""
    message = f"{timestamp}.".encode() + body_bytes
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


async def dispatch_webhooks(
    session: AsyncSession,
    webhook_urls: list[str],
    webhook_secret: str = "",
) -> int:
    """Dispatch webhook notifications for unnotified critical/high alerts.

    Returns the number of alerts processed.
    """
    # Find unnotified high/critical alerts
    result = await session.execute(
        select(Alert).where(
            Alert.notified_at.is_(None),
            Alert.severity.in_(["critical", "high"]),
        )
    )
    alerts = result.scalars().all()

    if not alerts or not webhook_urls:
        return 0

    # Pre-fetch hive names
    hive_ids = {a.hive_id for a in alerts}
    hive_names: dict[int, str] = {}
    for hive_id in hive_ids:
        hive = await session.get(Hive, hive_id)
        if hive:
            hive_names[hive_id] = hive.name

    count = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for alert in alerts:
            payload = _build_payload(alert, hive_names.get(alert.hive_id))
            body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            timestamp = str(int(time.time()))

            headers = {
                "Content-Type": "application/json",
                "X-Waggle-Timestamp": timestamp,
            }
            if webhook_secret:
                sig = _sign_payload(webhook_secret, timestamp, body_bytes)
                headers["X-Waggle-Signature"] = f"sha256={sig}"

            for url in webhook_urls:
                try:
                    await client.post(url, content=body_bytes, headers=headers)
                except Exception:
                    pass  # Single attempt, no retries

            # Set notified_at regardless of delivery outcome
            alert.notified_at = utc_now()
            count += 1

    await session.commit()
    return count
