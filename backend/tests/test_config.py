"""Tests for configuration loading."""

import pytest
from pydantic import ValidationError

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
    with pytest.raises(ValueError, match="TRUST_PROXY.*127.0.0.1"):
        Settings(API_KEY="test-key-123", TRUST_PROXY=True, API_HOST="0.0.0.0", _env_file=None)


def test_settings_api_key_required():
    """API_KEY is required."""
    with pytest.raises(Exception):
        Settings(_env_file=None)


def test_phase3_config_defaults():
    """Phase 3 config fields have correct defaults."""
    s = Settings(API_KEY="test", _env_file=None)
    assert s.MAX_QUEUE_DEPTH == 50
    assert s.DISK_USAGE_THRESHOLD == 0.90
    assert s.MAX_PHOTO_SIZE == 204800
    assert s.PHOTO_DIR == "/var/lib/waggle/photos"
    assert s.PHOTO_RETENTION_DAYS == 30
    assert s.DETECTION_CONFIDENCE_THRESHOLD == 0.25
    assert s.WEBHOOK_URLS == []
    assert s.WEBHOOK_SECRET == ""
    assert s.WEATHER_PROVIDER == "none"
    assert s.LOCAL_SIGNING_TTL_SEC == 600
    assert s.FASTAPI_BASE_URL == "http://localhost:8000"
    assert s.SYNC_INTERVAL_SEC == 300


def test_weather_provider_owm_alias():
    """WEATHER_PROVIDER 'owm' normalizes to 'openweathermap'."""
    s = Settings(API_KEY="test", WEATHER_PROVIDER="owm", _env_file=None)
    assert s.WEATHER_PROVIDER == "openweathermap"


def test_weather_provider_invalid():
    """Invalid WEATHER_PROVIDER raises validation error."""
    with pytest.raises(ValidationError):
        Settings(API_KEY="test", WEATHER_PROVIDER="invalid", _env_file=None)


def test_webhook_urls_parsing():
    """WEBHOOK_URLS parses comma-separated string."""
    s = Settings(API_KEY="test", WEBHOOK_URLS="https://a.com,https://b.com", _env_file=None)
    assert s.WEBHOOK_URLS == ["https://a.com", "https://b.com"]
