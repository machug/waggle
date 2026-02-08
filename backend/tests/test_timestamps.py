"""Tests for timestamp utilities."""

import re
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from waggle.utils.timestamps import utc_now, validate_observed_at, is_system_time_valid

# Canonical format: YYYY-MM-DDTHH:MM:SS.mmmZ
ISO_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")


def test_utc_now_format():
    """utc_now() should return canonical ISO 8601 with milliseconds."""
    result = utc_now()
    assert ISO_PATTERN.match(result), f"Bad format: {result}"


def test_utc_now_is_utc():
    """utc_now() should be within a second of actual UTC."""
    result = utc_now()
    # Parse it back
    dt = datetime.strptime(result, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    assert abs((now - dt).total_seconds()) < 2


def test_validate_observed_at_valid():
    """Recent timestamp should be valid."""
    ts = utc_now()
    assert validate_observed_at(ts) is True


def test_validate_observed_at_bad_format():
    """Non-ISO string should be invalid."""
    assert validate_observed_at("not-a-timestamp") is False


def test_validate_observed_at_future():
    """Future timestamp should be invalid."""
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    assert validate_observed_at(future) is False


def test_validate_observed_at_too_old():
    """Timestamp older than max_past_skew_hours should be invalid."""
    old = (datetime.now(timezone.utc) - timedelta(hours=73)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    assert validate_observed_at(old, max_past_skew_hours=72) is False


def test_validate_observed_at_within_skew():
    """Timestamp within skew window should be valid."""
    recent = (datetime.now(timezone.utc) - timedelta(hours=71)).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"
    assert validate_observed_at(recent, max_past_skew_hours=72) is True


def test_is_system_time_valid_current():
    """Current system time should be valid."""
    assert is_system_time_valid(min_year=2025) is True


def test_is_system_time_valid_old():
    """System time before min_year should be invalid."""
    assert is_system_time_valid(min_year=3000) is False
