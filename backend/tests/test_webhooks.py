"""Tests for webhook notification dispatcher."""

import hashlib
import hmac as hmac_mod
import json
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from waggle.database import create_engine_from_url, init_db
from waggle.models import Alert, Hive
from waggle.services.notify import _build_payload, _sign_payload, dispatch_webhooks
from waggle.utils.timestamps import utc_now


@pytest.fixture
async def engine(tmp_path):
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    eng = create_engine_from_url(url)
    await init_db(eng)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine):
    async with AsyncSession(engine) as session:
        yield session


async def _seed_hive(session, hive_id=1, name="Test Hive"):
    """Seed a hive if it doesn't already exist."""
    hive = await session.get(Hive, hive_id)
    if not hive:
        hive = Hive(id=hive_id, name=name, created_at=utc_now())
        session.add(hive)
        await session.commit()
    return hive


async def _seed_alert(session, severity="high", notified_at=None, hive_id=1):
    """Seed a hive and alert, return the alert."""
    await _seed_hive(session, hive_id)
    now = utc_now()
    alert = Alert(
        hive_id=hive_id,
        type="VARROA_DETECTED",
        severity=severity,
        message="Test alert",
        observed_at=now,
        created_at=now,
        updated_at=now,
    )
    if notified_at:
        alert.notified_at = notified_at
    session.add(alert)
    await session.commit()
    await session.refresh(alert)
    return alert


# --- Unit tests for helper functions ---


def test_build_payload():
    """Payload includes all required fields."""

    class FakeAlert:
        id = 1
        type = "VARROA_DETECTED"
        severity = "high"
        hive_id = 1
        message = "Test"
        observed_at = "2026-02-08T12:00:00.000Z"
        created_at = "2026-02-08T12:00:01.000Z"
        details_json = '{"varroa_count": 5}'

    payload = _build_payload(FakeAlert(), "Hive Alpha")
    assert payload["alert_id"] == 1
    assert payload["type"] == "VARROA_DETECTED"
    assert payload["severity"] == "high"
    assert payload["hive_id"] == 1
    assert payload["hive_name"] == "Hive Alpha"
    assert payload["message"] == "Test"
    assert payload["observed_at"] == "2026-02-08T12:00:00.000Z"
    assert payload["created_at"] == "2026-02-08T12:00:01.000Z"
    assert payload["details"] == {"varroa_count": 5}


def test_build_payload_none_details():
    """Payload with no details_json returns None for details."""

    class FakeAlert:
        id = 2
        type = "HIGH_TEMP"
        severity = "critical"
        hive_id = 1
        message = "Too hot"
        observed_at = "2026-02-08T12:00:00.000Z"
        created_at = "2026-02-08T12:00:01.000Z"
        details_json = None

    payload = _build_payload(FakeAlert(), None)
    assert payload["details"] is None
    assert payload["hive_name"] is None


def test_sign_payload():
    """HMAC-SHA256 is computed over 'timestamp.json_body'."""
    secret = "test-secret"
    timestamp = "1234567890"
    body = b'{"test":"data"}'
    sig = _sign_payload(secret, timestamp, body)
    # Verify independently
    expected = hmac_mod.new(
        secret.encode(),
        f"{timestamp}.".encode() + body,
        hashlib.sha256,
    ).hexdigest()
    assert sig == expected


def test_sign_payload_different_secrets_differ():
    """Different secrets produce different signatures."""
    body = b'{"test":"data"}'
    ts = "1234567890"
    sig1 = _sign_payload("secret-a", ts, body)
    sig2 = _sign_payload("secret-b", ts, body)
    assert sig1 != sig2


def test_sign_payload_different_timestamps_differ():
    """Different timestamps produce different signatures."""
    body = b'{"test":"data"}'
    sig1 = _sign_payload("secret", "1111111111", body)
    sig2 = _sign_payload("secret", "2222222222", body)
    assert sig1 != sig2


# --- Integration tests for dispatch_webhooks ---


async def test_dispatch_skips_low_severity(db_session):
    """Low/medium severity alerts are not dispatched."""
    await _seed_alert(db_session, severity="low")
    await _seed_alert(db_session, severity="medium")
    count = await dispatch_webhooks(db_session, ["http://localhost:1/webhook"], "")
    assert count == 0


async def test_dispatch_skips_already_notified(db_session):
    """Already notified alerts are not re-dispatched."""
    await _seed_alert(db_session, severity="high", notified_at=utc_now())
    count = await dispatch_webhooks(db_session, ["http://localhost:1/webhook"], "")
    assert count == 0


async def test_dispatch_returns_zero_for_no_urls(db_session):
    """When no webhook URLs configured, nothing is dispatched."""
    await _seed_alert(db_session, severity="critical")
    count = await dispatch_webhooks(db_session, [], "secret")
    assert count == 0


async def test_dispatch_sets_notified_at(db_session):
    """notified_at is set after dispatch attempt, even on connection failure."""
    alert = await _seed_alert(db_session, severity="critical")
    assert alert.notified_at is None

    # Use a URL that will fail to connect — notified_at should still be set
    count = await dispatch_webhooks(
        db_session, ["http://localhost:1/webhook"], ""
    )
    assert count == 1
    await db_session.refresh(alert)
    assert alert.notified_at is not None


async def test_dispatch_processes_multiple_alerts(db_session):
    """Multiple critical/high alerts are all processed."""
    await _seed_alert(db_session, severity="critical")
    await _seed_alert(db_session, severity="high")
    await _seed_alert(db_session, severity="low")  # Should be skipped
    count = await dispatch_webhooks(
        db_session, ["http://localhost:1/webhook"], ""
    )
    assert count == 2


async def test_dispatch_sends_to_all_urls(db_session):
    """All configured URLs receive a POST for each alert."""
    await _seed_alert(db_session, severity="high")

    posted_urls = []

    async def mock_post(self, url, **kwargs):
        posted_urls.append(str(url))
        # Return a mock response
        return type("Response", (), {"status_code": 200})()

    with patch("httpx.AsyncClient.post", new=mock_post):
        count = await dispatch_webhooks(
            db_session,
            ["http://hook1.example.com", "http://hook2.example.com"],
            "test-secret",
        )

    assert count == 1
    assert len(posted_urls) == 2
    assert "http://hook1.example.com" in posted_urls
    assert "http://hook2.example.com" in posted_urls


async def test_dispatch_includes_signature_header(db_session):
    """When webhook_secret is set, X-Waggle-Signature header is included."""
    await _seed_alert(db_session, severity="high")

    captured_headers = {}

    async def mock_post(self, url, *, content=None, headers=None, **kwargs):
        captured_headers.update(headers or {})
        return type("Response", (), {"status_code": 200})()

    with patch("httpx.AsyncClient.post", new=mock_post):
        await dispatch_webhooks(
            db_session,
            ["http://hook.example.com"],
            "my-secret",
        )

    assert "X-Waggle-Signature" in captured_headers
    assert captured_headers["X-Waggle-Signature"].startswith("sha256=")
    assert "X-Waggle-Timestamp" in captured_headers


async def test_dispatch_no_signature_without_secret(db_session):
    """When webhook_secret is empty, X-Waggle-Signature header is NOT included."""
    await _seed_alert(db_session, severity="high")

    captured_headers = {}

    async def mock_post(self, url, *, content=None, headers=None, **kwargs):
        captured_headers.update(headers or {})
        return type("Response", (), {"status_code": 200})()

    with patch("httpx.AsyncClient.post", new=mock_post):
        await dispatch_webhooks(
            db_session,
            ["http://hook.example.com"],
            "",  # No secret
        )

    assert "X-Waggle-Signature" not in captured_headers
    assert "X-Waggle-Timestamp" in captured_headers


async def test_dispatch_payload_contains_hive_name(db_session):
    """Webhook payload includes the hive name from the database."""
    await _seed_alert(db_session, severity="high")

    captured_body = None

    async def mock_post(self, url, *, content=None, headers=None, **kwargs):
        nonlocal captured_body
        captured_body = content
        return type("Response", (), {"status_code": 200})()

    with patch("httpx.AsyncClient.post", new=mock_post):
        await dispatch_webhooks(
            db_session,
            ["http://hook.example.com"],
            "",
        )

    assert captured_body is not None
    payload = json.loads(captured_body)
    assert payload["hive_name"] == "Test Hive"
    assert payload["type"] == "VARROA_DETECTED"
    assert payload["severity"] == "high"
    assert payload["hive_id"] == 1


async def test_dispatch_signature_verifiable(db_session):
    """The signature in the header can be verified independently."""
    await _seed_alert(db_session, severity="critical")

    captured_body = None
    captured_headers = {}
    secret = "verify-me"

    async def mock_post(self, url, *, content=None, headers=None, **kwargs):
        nonlocal captured_body
        captured_body = content
        captured_headers.update(headers or {})
        return type("Response", (), {"status_code": 200})()

    with patch("httpx.AsyncClient.post", new=mock_post):
        await dispatch_webhooks(
            db_session,
            ["http://hook.example.com"],
            secret,
        )

    # Extract signature and timestamp from headers
    sig_header = captured_headers["X-Waggle-Signature"]
    timestamp = captured_headers["X-Waggle-Timestamp"]
    assert sig_header.startswith("sha256=")
    sig_hex = sig_header[len("sha256="):]

    # Recompute and verify
    message = f"{timestamp}.".encode() + captured_body
    expected = hmac_mod.new(
        secret.encode(), message, hashlib.sha256
    ).hexdigest()
    assert sig_hex == expected
