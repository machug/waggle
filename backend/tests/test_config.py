"""Tests for configuration loading."""

from waggle.config import Settings


def test_settings_defaults():
    """Settings should have sensible defaults."""
    s = Settings(API_KEY="test-key-123", _env_file=None)
    assert s.DB_PATH == "/var/lib/waggle/waggle.db"
    assert s.MQTT_HOST == "127.0.0.1"
    assert s.MQTT_PORT == 1883
    assert s.API_HOST == "127.0.0.1"
    assert s.API_PORT == 8000
    assert s.SERIAL_DEVICE == "/dev/ttyUSB0"
    assert s.SERIAL_BAUD == 115200
    assert s.WAKE_INTERVAL_SEC == 60
    assert s.MAX_PAST_SKEW_HOURS == 72
    assert s.MIN_VALID_YEAR == 2025
    assert s.RATE_LIMIT == "100/minute"
    assert s.TRUST_PROXY is False
    assert s.STATUS_AUTH is False
    assert s.CORS_ORIGIN is None


def test_settings_db_url():
    """DB_URL should be computed from DB_PATH."""
    s = Settings(API_KEY="test-key-123", DB_PATH="/tmp/test.db", _env_file=None)
    assert s.DB_URL == "sqlite+aiosqlite:////tmp/test.db"


def test_settings_trust_proxy_requires_localhost():
    """When TRUST_PROXY=true, API_HOST must be 127.0.0.1."""
    import pytest
    with pytest.raises(ValueError, match="TRUST_PROXY.*127.0.0.1"):
        Settings(API_KEY="test-key-123", TRUST_PROXY=True, API_HOST="0.0.0.0", _env_file=None)


def test_settings_api_key_required():
    """API_KEY is required."""
    import pytest
    with pytest.raises(Exception):
        Settings(_env_file=None)
