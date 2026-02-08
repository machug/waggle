"""Tests for Phase 3 app registration — router mounting, settings, admin auth, notify CLI."""

import sys
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport

from waggle.main import create_app


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "test.db"
    return create_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        api_key="test-key",
        admin_api_key="test-admin-key",
    )


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# -- Phase 3 route paths that must be present --
PHASE3_PATHS = [
    "/api/admin/camera-nodes",
    "/api/photos/upload",
    "/api/hives/{hive_id}/detections",
    "/api/hives/{hive_id}/varroa",
    "/api/varroa/overview",
    "/api/inspections",
    "/api/hives/{hive_id}/inspections",
    "/api/weather/current",
    "/api/sync/status",
]


def test_phase3_routers_mounted(app):
    """All Phase 3 router paths should be registered on the app."""
    route_paths = {route.path for route in app.routes if hasattr(route, "path")}
    for expected in PHASE3_PATHS:
        assert expected in route_paths, f"Missing route: {expected}"


def test_settings_on_app_state(tmp_path):
    """Settings object should be stored on app.state.settings."""
    db_path = tmp_path / "test.db"
    sentinel = {"marker": "test-settings"}
    app = create_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        api_key="test-key",
        settings=sentinel,
    )
    assert app.state.settings is sentinel


def test_settings_none_by_default(tmp_path):
    """When settings is not passed, app.state.settings should be None."""
    db_path = tmp_path / "test.db"
    app = create_app(
        db_url=f"sqlite+aiosqlite:///{db_path}",
        api_key="test-key",
    )
    assert app.state.settings is None


@pytest.mark.asyncio
async def test_admin_key_wired(client):
    """Admin router should return 401 without admin key."""
    resp = await client.post("/api/admin/camera-nodes", json={})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_admin_key_wrong(client):
    """Admin router should return 401 with wrong admin key."""
    resp = await client.post(
        "/api/admin/camera-nodes",
        json={},
        headers={"X-Admin-Key": "wrong-key"},
    )
    assert resp.status_code == 401


def test_notify_cli_command_exists():
    """The 'notify' CLI command should call run_notify."""
    with patch("waggle.__main__.run_notify") as mock_notify:
        with patch.object(sys, "argv", ["waggle", "notify"]):
            from waggle.__main__ import main

            main()
        mock_notify.assert_called_once()


def test_notify_dispatches_webhooks(tmp_path):
    """run_notify should create engine, session, and call dispatch_webhooks."""
    db_path = tmp_path / "test.db"
    mock_dispatch = AsyncMock(return_value=0)

    with (
        patch("waggle.__main__.Settings") as mock_settings_cls,
        patch("waggle.__main__.dispatch_webhooks", create=True, new=mock_dispatch),
        patch("waggle.services.notify.dispatch_webhooks", mock_dispatch),
    ):
        mock_settings = mock_settings_cls.return_value
        mock_settings.DB_URL = f"sqlite+aiosqlite:///{db_path}"
        mock_settings.WEBHOOK_URLS = ["http://example.com/hook"]
        mock_settings.WEBHOOK_SECRET = "secret"

        from waggle.__main__ import run_notify

        run_notify()

    mock_dispatch.assert_called_once()


def test_cli_usage_includes_notify():
    """Usage string should mention 'notify' command."""
    from waggle.__main__ import main

    with (
        patch.object(sys, "argv", ["waggle", "unknown-command"]),
        patch("builtins.print") as mock_print,
        pytest.raises(SystemExit),
    ):
        main()

    usage_calls = [str(c) for c in mock_print.call_args_list]
    usage_text = " ".join(usage_calls)
    assert "notify" in usage_text
