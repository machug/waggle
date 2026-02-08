"""Tests for hives CRUD endpoints."""



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
