"""Tests for alerts endpoints."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import Alert, Hive
from waggle.utils.timestamps import utc_now


async def _create_hive_and_alerts(client, auth_headers, count=3):
    """Create a hive and insert alerts directly via DB."""
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    engine = client._transport.app.state.engine
    async with AsyncSession(engine) as session:
        for i in range(count):
            alert_types = ["HIGH_TEMP", "LOW_TEMP", "LOW_BATTERY"]
            severities = ["high", "medium", "low"]
            alert = Alert(
                hive_id=1,
                type=alert_types[i % 3],
                severity=severities[i % 3],
                message=f"Test alert {i}",
                created_at=f"2026-02-07T{10+i:02d}:00:00.000Z",
            )
            session.add(alert)
        await session.commit()


async def test_list_alerts_empty(client, auth_headers):
    resp = await client.get("/api/alerts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_alerts(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers, count=3)
    resp = await client.get("/api/alerts", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    # Ordered by created_at DESC
    assert body["items"][0]["created_at"] >= body["items"][-1]["created_at"]


async def test_list_alerts_filter_by_hive(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers)
    resp = await client.get("/api/alerts?hive_id=1", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 3

    resp = await client.get("/api/alerts?hive_id=99", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 0


async def test_list_alerts_filter_by_type(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers)
    resp = await client.get("/api/alerts?type=HIGH_TEMP", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "HIGH_TEMP"


async def test_list_alerts_filter_by_severity(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers)
    resp = await client.get("/api/alerts?severity=high", headers=auth_headers)
    body = resp.json()
    assert all(item["severity"] == "high" for item in body["items"])


async def test_list_alerts_filter_by_acknowledged(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers)
    resp = await client.get("/api/alerts?acknowledged=false", headers=auth_headers)
    body = resp.json()
    assert body["total"] == 3  # All unacknowledged initially


async def test_acknowledge_alert(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers, count=1)
    resp = await client.patch(
        "/api/alerts/1/acknowledge",
        json={"acknowledged_by": "beekeeper"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["acknowledged"] is True
    assert body["acknowledged_by"] == "beekeeper"
    assert body["acknowledged_at"] is not None


async def test_acknowledge_idempotent(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers, count=1)
    # Acknowledge once
    await client.patch("/api/alerts/1/acknowledge", json={}, headers=auth_headers)
    # Acknowledge again - should be idempotent
    resp = await client.patch("/api/alerts/1/acknowledge", json={}, headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["acknowledged"] is True


async def test_acknowledge_not_found(client, auth_headers):
    resp = await client.patch("/api/alerts/99/acknowledge", json={}, headers=auth_headers)
    assert resp.status_code == 404


async def test_pagination(client, auth_headers):
    await _create_hive_and_alerts(client, auth_headers, count=3)
    resp = await client.get("/api/alerts?limit=1&offset=0", headers=auth_headers)
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["total"] == 3
