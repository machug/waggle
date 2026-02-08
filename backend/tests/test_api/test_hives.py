"""Tests for hives CRUD endpoints."""

from sqlalchemy.ext.asyncio import AsyncSession


async def test_create_hive(client, auth_headers):
    resp = await client.post(
        "/api/hives",
        json={"id": 1, "name": "Hive Alpha", "location": "Backyard east"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] == 1
    assert body["name"] == "Hive Alpha"
    assert body["last_seen_at"] is None
    assert "created_at" in body


async def test_create_hive_duplicate_id(client, auth_headers):
    await client.post("/api/hives", json={"id": 1, "name": "A"}, headers=auth_headers)
    resp = await client.post("/api/hives", json={"id": 1, "name": "B"}, headers=auth_headers)
    assert resp.status_code == 409


async def test_create_hive_invalid_id(client, auth_headers):
    resp = await client.post("/api/hives", json={"id": 0, "name": "Bad"}, headers=auth_headers)
    assert resp.status_code == 422


async def test_list_hives_empty(client, auth_headers):
    resp = await client.get("/api/hives", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_list_hives_with_data(client, auth_headers):
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    await client.post("/api/hives", json={"id": 2, "name": "Beta"}, headers=auth_headers)
    resp = await client.get("/api/hives", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert body["items"][0]["name"] == "Alpha"


async def test_list_hives_includes_latest_reading(client, auth_headers):
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    resp = await client.get("/api/hives", headers=auth_headers)
    body = resp.json()
    assert body["items"][0]["latest_reading"] is None


async def test_get_hive(client, auth_headers):
    await client.post(
        "/api/hives",
        json={"id": 1, "name": "Alpha", "sender_mac": "AA:BB:CC:DD:EE:FF"},
        headers=auth_headers,
    )
    resp = await client.get("/api/hives/1", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["sender_mac"] == "AA:BB:CC:DD:EE:FF"


async def test_get_hive_not_found(client, auth_headers):
    resp = await client.get("/api/hives/99", headers=auth_headers)
    assert resp.status_code == 404


async def test_patch_hive(client, auth_headers):
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    resp = await client.patch(
        "/api/hives/1",
        json={"name": "Alpha Prime", "location": "Rooftop"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Alpha Prime"
    assert body["location"] == "Rooftop"


async def test_patch_hive_clear_nullable(client, auth_headers):
    await client.post(
        "/api/hives",
        json={"id": 1, "name": "Alpha", "location": "Here"},
        headers=auth_headers,
    )
    resp = await client.patch(
        "/api/hives/1", json={"location": None}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["location"] is None


async def test_delete_hive_empty(client, auth_headers):
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    resp = await client.delete("/api/hives/1", headers=auth_headers)
    assert resp.status_code == 204


async def test_delete_hive_not_found(client, auth_headers):
    resp = await client.delete("/api/hives/99", headers=auth_headers)
    assert resp.status_code == 404


async def test_pagination(client, auth_headers):
    for i in range(1, 6):
        await client.post(
            "/api/hives", json={"id": i, "name": f"Hive {i:02d}"}, headers=auth_headers
        )
    resp = await client.get("/api/hives?limit=2&offset=0", headers=auth_headers)
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["total"] == 5


# --- Phase 2 traffic fields ---


async def test_hive_list_latest_traffic_null(client, auth_headers):
    """Hive list returns latest_traffic: null for hive without bee counts."""
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    resp = await client.get("/api/hives", headers=auth_headers)
    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["latest_traffic"] is None
    assert item["activity_score_today"] is None


async def test_hive_list_latest_traffic_with_data(client, auth_headers):
    """Hive list returns latest_traffic when bee_counts exist."""
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)

    # Insert reading + bee_count directly
    engine = client._transport.app.state.engine
    async with AsyncSession(engine) as session:
        from waggle.models import BeeCount, SensorReading
        from waggle.utils.timestamps import utc_now
        reading = SensorReading(
            hive_id=1, observed_at=utc_now(), ingested_at=utc_now(),
            weight_kg=30.0, temp_c=35.0, humidity_pct=50.0,
            pressure_hpa=1013.0, battery_v=3.7, sequence=1,
            flags=0, sender_mac="AA:BB:CC:DD:EE:FF",
        )
        session.add(reading)
        await session.flush()
        bc = BeeCount(
            reading_id=reading.id, hive_id=1, observed_at=reading.observed_at,
            ingested_at=reading.ingested_at, period_ms=60000,
            bees_in=100, bees_out=150, lane_mask=15, stuck_mask=0,
            sequence=1, flags=0, sender_mac="AA:BB:CC:DD:EE:FF",
        )
        session.add(bc)
        await session.commit()

    resp = await client.get("/api/hives", headers=auth_headers)
    item = resp.json()["items"][0]
    assert item["latest_traffic"] is not None
    assert item["latest_traffic"]["bees_in"] == 100
    assert item["latest_traffic"]["bees_out"] == 150
    assert item["latest_traffic"]["net_out"] == 50
    assert item["latest_traffic"]["total_traffic"] == 250


async def test_hive_detail_has_traffic_fields(client, auth_headers):
    """GET /api/hives/{id} returns traffic fields."""
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    resp = await client.get("/api/hives/1", headers=auth_headers)
    body = resp.json()
    assert "latest_traffic" in body
    assert "activity_score_today" in body


async def test_hive_detail_activity_score_null_insufficient_history(client, auth_headers):
    """activity_score_today is null when insufficient traffic history."""
    await client.post("/api/hives", json={"id": 1, "name": "Alpha"}, headers=auth_headers)
    resp = await client.get("/api/hives/1", headers=auth_headers)
    assert resp.json()["activity_score_today"] is None
