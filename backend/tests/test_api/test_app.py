"""Tests for FastAPI app shell and error handling."""


async def test_404_returns_error_schema(client, auth_headers):
    resp = await client.get("/api/nonexistent", headers=auth_headers)
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"


async def test_unauthorized_returns_error_schema(client):
    resp = await client.get("/api/hives")
    assert resp.status_code == 401
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == "UNAUTHORIZED"
