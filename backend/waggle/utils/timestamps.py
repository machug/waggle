"""Timestamp utilities for canonical ISO 8601 formatting and validation."""

from datetime import UTC, datetime, timedelta


def utc_now() -> str:
    """Return current UTC time as canonical ISO 8601 string: YYYY-MM-DDTHH:MM:SS.mmmZ"""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def validate_observed_at(observed_at: str, *, max_past_skew_hours: int = 72) -> bool:
    """Validate an observed_at timestamp string.

    Returns True if:
    - Format matches YYYY-MM-DDTHH:MM:SS.mmmZ
    - Not in the future
    - Not older than max_past_skew_hours
    """
    try:
        dt = datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=UTC
        )
    except (ValueError, TypeError):
        return False

    now = datetime.now(UTC)

    # Not in the future (small tolerance for clock skew)
    if dt > now + timedelta(seconds=30):
        return False

    # Not too old
    if dt < now - timedelta(hours=max_past_skew_hours):
        return False

    return True


def is_system_time_valid(min_year: int = 2025) -> bool:
    """Check if system clock is set to a reasonable time."""
    return datetime.now(UTC).year >= min_year
