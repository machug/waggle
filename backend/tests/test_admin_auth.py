"""Tests for admin key authentication."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from waggle.auth import (
    create_admin_key_dependency,
    install_auth_error_handler,
)


@pytest.fixture
def admin_app():
    """Create a minimal FastAPI app with admin auth for testing."""
    app = FastAPI()
    install_auth_error_handler(app)
    verify_admin = create_admin_key_dependency("test-admin-secret")

    @app.get("/admin/test", dependencies=[verify_admin])
    async def admin_test():
        return {"ok": True}

    return app


@pytest.fixture
def admin_client(admin_app):
    return TestClient(admin_app)


@pytest.fixture
def disabled_admin_app():
    """App where admin key is not configured (None)."""
    app = FastAPI()
    install_auth_error_handler(app)
    verify_admin = create_admin_key_dependency(None)

    @app.get("/admin/test", dependencies=[verify_admin])
    async def admin_test():
        return {"ok": True}

    return app


@pytest.fixture
def disabled_admin_client(disabled_admin_app):
    return TestClient(disabled_admin_app)


def test_admin_key_valid(admin_client):
    resp = admin_client.get(
        "/admin/test", headers={"X-Admin-Key": "test-admin-secret"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_admin_key_missing(admin_client):
    resp = admin_client.get("/admin/test")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


def test_admin_key_wrong(admin_client):
    resp = admin_client.get(
        "/admin/test", headers={"X-Admin-Key": "wrong-key"}
    )
    assert resp.status_code == 401


def test_regular_api_key_not_admin(admin_client):
    """X-API-Key header should not work for admin endpoints."""
    resp = admin_client.get(
        "/admin/test", headers={"X-API-Key": "test-admin-secret"}
    )
    assert resp.status_code == 401


def test_admin_disabled_when_no_key(disabled_admin_client):
    """When ADMIN_API_KEY is not set, admin endpoints return 401."""
    resp = disabled_admin_client.get(
        "/admin/test", headers={"X-Admin-Key": "anything"}
    )
    assert resp.status_code == 401
    assert "not configured" in resp.json()["error"]["message"]
