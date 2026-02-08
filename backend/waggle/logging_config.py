"""Structured logging configuration using structlog with JSON output.

Configures structlog for JSON logging to stdout, suitable for capture
by systemd/journald. Each log entry includes the service name, timestamp,
log level, and event message.
"""

from __future__ import annotations

import logging
import sys

import structlog


def configure_logging(service_name: str, level: str = "INFO") -> None:
    """Configure structlog with JSON rendering for a named service.

    Args:
        service_name: Bound to every log entry (e.g. "bridge", "worker", "api").
        level: Root log level as a string (e.g. "DEBUG", "INFO", "WARNING").
    """
    # Validate level string early
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {level!r}")

    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *processors,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=False,
    )

    # Set stdlib root logger level so that structlog respects the threshold
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
    )

    # Bind service_name globally so every log entry includes it
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(service=service_name)
