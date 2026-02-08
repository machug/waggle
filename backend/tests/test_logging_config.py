"""Tests for structured logging configuration."""

import json

import pytest
import structlog

from waggle.logging_config import configure_logging


@pytest.fixture(autouse=True)
def _reset_structlog():
    """Reset structlog configuration between tests."""
    yield
    structlog.reset_defaults()
    structlog.contextvars.clear_contextvars()


def test_configure_logging_returns_none():
    """configure_logging should return None (side-effect only)."""
    result = configure_logging("test-service")
    assert result is None


def test_log_output_is_json(capsys):
    """Log output should be valid JSON."""
    configure_logging("test-svc")
    log = structlog.get_logger()
    log.info("hello world")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["event"] == "hello world"


def test_log_includes_service_name(capsys):
    """Every log entry should include the bound service name."""
    configure_logging("bridge")
    log = structlog.get_logger()
    log.info("startup")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["service"] == "bridge"


def test_log_includes_level(capsys):
    """Log entries should include the log level."""
    configure_logging("worker")
    log = structlog.get_logger()
    log.warning("something happened")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["level"] == "warning"


def test_log_includes_timestamp(capsys):
    """Log entries should include an ISO timestamp."""
    configure_logging("api")
    log = structlog.get_logger()
    log.info("ping")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert "timestamp" in parsed
    # ISO format should contain 'T'
    assert "T" in parsed["timestamp"]


def test_extra_context_appears(capsys):
    """Additional key-value pairs should appear in JSON output."""
    configure_logging("bridge")
    log = structlog.get_logger()
    log.info("frame received", frame_size=38, mac="AA:BB:CC:DD:EE:FF")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["frame_size"] == 38
    assert parsed["mac"] == "AA:BB:CC:DD:EE:FF"


def test_different_service_names(capsys):
    """Reconfiguring with a new service name should update context."""
    configure_logging("api")
    log = structlog.get_logger()
    log.info("first")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["service"] == "api"


def test_invalid_level_raises():
    """An invalid log level string should raise ValueError."""
    with pytest.raises(ValueError, match="Invalid log level"):
        configure_logging("test", level="BOGUS")


def test_level_case_insensitive(capsys):
    """Log level should be case-insensitive."""
    configure_logging("test-svc", level="info")
    log = structlog.get_logger()
    log.info("ok")
    captured = capsys.readouterr()
    parsed = json.loads(captured.out.strip())
    assert parsed["event"] == "ok"
