"""Tests for API key authentication dependency."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from waggle.auth import create_api_key_dependency, install_auth_error_handler


def _make_app(api_key: str) -> FastAPI:
    app = FastAPI()
    install_auth_error_handler(app)
    verify_key = create_api_key_dependency(api_key)

    @app.get("/protected")
    async def protected(key: str = verify_key):
        return {"ok": True}

    return app


def test_valid_key():
    client = TestClient(_make_app("test-key-123"))
    resp = client.get("/protected", headers={"X-API-Key": "test-key-123"})
    assert resp.status_code == 200


def test_missing_key():
    client = TestClient(_make_app("test-key-123"))
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_wrong_key():
    client = TestClient(_make_app("test-key-123"))
    resp = client.get("/protected", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_constant_time_comparison():
    """Key comparison should use hmac.compare_digest (timing-safe)."""
    import inspect

    from waggle.auth import create_api_key_dependency
    source = inspect.getsource(create_api_key_dependency)
    assert "compare_digest" in source
