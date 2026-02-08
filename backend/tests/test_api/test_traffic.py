"""Tests for traffic API endpoints."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.models import BeeCount, SensorReading


async def _seed_hive_and_traffic(client, auth_headers, engine, count=5, hive_id=1):
    """Create a hive with sensor readings and bee_counts."""
    await client.post(
        "/api/hives",
        json={"id": hive_id, "name": f"Hive {hive_id}"},
        headers=auth_headers,
    )

    async with AsyncSession(engine) as session:
        now = datetime.now(UTC)
        for i in range(count):
            obs = (
                (now - timedelta(minutes=count - i)).strftime("%Y-%m-%dT%H:%M:%S.%f")[
                    :-3
                ]
                + "Z"
            )
            ing = obs
            reading = SensorReading(
                hive_id=hive_id,
                observed_at=obs,
                ingested_at=ing,
                weight_kg=30.0,
                temp_c=35.0,
                humidity_pct=50.0,
                pressure_hpa=1013.0,
                battery_v=3.7,
                sequence=i,
                flags=0,
                sender_mac="AA:BB:CC:DD:EE:FF",
            )
            session.add(reading)
            await session.flush()

            bc = BeeCount(
                reading_id=reading.id,
                hive_id=hive_id,
                observed_at=obs,
                ingested_at=ing,
                period_ms=60000,
                bees_in=100 + i * 10,
                bees_out=120 + i * 10,
                lane_mask=15,
                stuck_mask=0,
                sequence=i,
                flags=0,
                sender_mac="AA:BB:CC:DD:EE:FF",
            )
            session.add(bc)
        await session.commit()


async def _seed_multi_day_traffic(client, auth_headers, engine, hive_id=1, days=5):
    """Create traffic data spanning multiple days for summary/activity tests."""
    await client.post(
        "/api/hives",
        json={"id": hive_id, "name": f"Hive {hive_id}"},
        headers=auth_headers,
    )

    async with AsyncSession(engine) as session:
        today = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)
        seq = 0
        for day_offset in range(days):
            day = today - timedelta(days=day_offset)
            # 3 readings per day at different hours
            for hour_offset in range(3):
                obs_dt = day.replace(hour=9 + hour_offset)
                obs = obs_dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
                reading = SensorReading(
                    hive_id=hive_id,
                    observed_at=obs,
                    ingested_at=obs,
                    weight_kg=30.0,
                    temp_c=35.0,
                    humidity_pct=50.0,
                    pressure_hpa=1013.0,
                    battery_v=3.7,
                    sequence=seq,
                    flags=0,
                    sender_mac="AA:BB:CC:DD:EE:FF",
                )
                session.add(reading)
                await session.flush()

                bc = BeeCount(
                    reading_id=reading.id,
                    hive_id=hive_id,
                    observed_at=obs,
                    ingested_at=obs,
                    period_ms=60000,
                    bees_in=50 + day_offset * 10,
                    bees_out=60 + day_offset * 10,
                    lane_mask=15,
                    stuck_mask=0,
                    sequence=seq,
                    flags=0,
                    sender_mac="AA:BB:CC:DD:EE:FF",
                )
                session.add(bc)
                seq += 1
        await session.commit()


@pytest.mark.anyio
async def test_traffic_raw_empty(client, auth_headers, app):
    """GET /api/hives/1/traffic with no data returns 200 and empty items."""
    await client.post(
        "/api/hives", json={"id": 1, "name": "Hive 1"}, headers=auth_headers
    )
    resp = await client.get("/api/hives/1/traffic", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["interval"] == "raw"


@pytest.mark.anyio
async def test_traffic_raw_with_data(client, auth_headers, app):
    """GET /api/hives/1/traffic with seeded data returns TrafficRecordOut items."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)
    resp = await client.get("/api/hives/1/traffic", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 5
    assert body["interval"] == "raw"
    # Check structure of a raw record
    item = body["items"][0]
    assert "id" in item
    assert "reading_id" in item
    assert "bees_in" in item
    assert "bees_out" in item
    assert "net_out" in item
    assert "total_traffic" in item
    # Default order is desc
    assert body["items"][0]["observed_at"] >= body["items"][-1]["observed_at"]


@pytest.mark.anyio
async def test_traffic_hourly_aggregation(client, auth_headers, app):
    """GET /api/hives/1/traffic?interval=hourly returns hourly aggregates."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)
    resp = await client.get(
        "/api/hives/1/traffic?interval=hourly", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == "hourly"
    assert body["total"] >= 1
    item = body["items"][0]
    assert "period_start" in item
    assert "period_end" in item
    assert "reading_count" in item
    assert "sum_bees_in" in item
    assert "avg_bees_in_per_min" in item


@pytest.mark.anyio
async def test_traffic_daily_aggregation(client, auth_headers, app):
    """GET /api/hives/1/traffic?interval=daily returns daily aggregates."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)
    resp = await client.get(
        "/api/hives/1/traffic?interval=daily", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["interval"] == "daily"
    # All 5 records are within minutes of each other — same day
    assert body["total"] == 1
    item = body["items"][0]
    assert item["reading_count"] == 5
    assert item["sum_bees_in"] == sum(100 + i * 10 for i in range(5))
    assert item["sum_bees_out"] == sum(120 + i * 10 for i in range(5))


@pytest.mark.anyio
async def test_traffic_time_range(client, auth_headers, app):
    """GET /api/hives/1/traffic?from=X&to=Y filters results by time range."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)

    # Get all data first to know the time bounds
    resp = await client.get(
        "/api/hives/1/traffic?order=asc", headers=auth_headers
    )
    all_items = resp.json()["items"]
    assert len(all_items) == 5

    # Use the 2nd item's time as 'from' and 4th item's time as 'to'
    from_time = all_items[1]["observed_at"]
    to_time = all_items[3]["observed_at"]

    resp = await client.get(
        f"/api/hives/1/traffic?from={from_time}&to={to_time}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3  # items at index 1, 2, 3


@pytest.mark.anyio
async def test_traffic_pagination(client, auth_headers, app):
    """limit=2&offset=0, then offset=2 returns proper pages."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)

    resp = await client.get(
        "/api/hives/1/traffic?limit=2&offset=0", headers=auth_headers
    )
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 0
    first_page_ids = [item["id"] for item in body["items"]]

    resp = await client.get(
        "/api/hives/1/traffic?limit=2&offset=2", headers=auth_headers
    )
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5
    assert body["offset"] == 2
    second_page_ids = [item["id"] for item in body["items"]]

    # No overlap between pages
    assert set(first_page_ids).isdisjoint(set(second_page_ids))


@pytest.mark.anyio
async def test_traffic_order_asc(client, auth_headers, app):
    """order=asc returns ascending by observed_at."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)

    resp = await client.get(
        "/api/hives/1/traffic?order=asc", headers=auth_headers
    )
    assert resp.status_code == 200
    body = resp.json()
    timestamps = [item["observed_at"] for item in body["items"]]
    assert timestamps == sorted(timestamps)


@pytest.mark.anyio
async def test_traffic_nonexistent_hive(client, auth_headers):
    """GET /api/hives/999/traffic returns 404."""
    resp = await client.get("/api/hives/999/traffic", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_traffic_no_auth(client):
    """No X-API-Key header returns 401."""
    resp = await client.get("/api/hives/1/traffic")
    assert resp.status_code == 401


@pytest.mark.anyio
async def test_traffic_latest(client, auth_headers, app):
    """GET /api/hives/1/traffic/latest returns single latest record."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)

    resp = await client.get("/api/hives/1/traffic/latest", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert "bees_in" in body
    assert "bees_out" in body
    # Latest should have the highest bees_in value (100 + 4*10 = 140)
    assert body["bees_in"] == 140
    assert body["bees_out"] == 160


@pytest.mark.anyio
async def test_traffic_latest_no_data(client, auth_headers):
    """GET /api/hives/1/traffic/latest with no data returns 404."""
    await client.post(
        "/api/hives", json={"id": 1, "name": "Hive 1"}, headers=auth_headers
    )
    resp = await client.get("/api/hives/1/traffic/latest", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_traffic_summary(client, auth_headers, app):
    """GET /api/hives/1/traffic/summary returns TrafficSummaryOut."""
    engine = app.state.engine
    await _seed_hive_and_traffic(client, auth_headers, engine, count=5)

    resp = await client.get("/api/hives/1/traffic/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "date" in body
    assert "total_in" in body
    assert "total_out" in body
    assert "net_out" in body
    assert "total_traffic" in body
    assert "peak_hour" in body
    # With only one day of data, rolling avg and activity score should be null
    assert body["rolling_7d_avg_total"] is None
    assert body["activity_score"] is None
    # Verify totals
    expected_in = sum(100 + i * 10 for i in range(5))
    expected_out = sum(120 + i * 10 for i in range(5))
    assert body["total_in"] == expected_in
    assert body["total_out"] == expected_out


@pytest.mark.anyio
async def test_traffic_summary_specific_date(client, auth_headers, app):
    """GET /api/hives/1/traffic/summary?date=YYYY-MM-DD returns summary for that date."""
    engine = app.state.engine
    await _seed_multi_day_traffic(client, auth_headers, engine, days=5)

    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    resp = await client.get(
        f"/api/hives/1/traffic/summary?date={today_str}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == today_str
    assert body["total_in"] > 0
    assert body["total_out"] > 0


@pytest.mark.anyio
async def test_activity_score_insufficient_history(client, auth_headers, app):
    """Activity score is null when less than 3 days of prior data exist."""
    engine = app.state.engine
    # Seed only 1 day of data — no prior days for rolling average
    await _seed_hive_and_traffic(client, auth_headers, engine, count=3)

    resp = await client.get("/api/hives/1/traffic/summary", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["activity_score"] is None
    assert body["rolling_7d_avg_total"] is None
