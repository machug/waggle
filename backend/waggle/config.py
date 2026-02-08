"""Application configuration via pydantic-settings."""

import sqlite3

from pydantic import model_validator
from pydantic_settings import BaseSettings

assert sqlite3.sqlite_version_info >= (3, 31, 0), (
    f"SQLite >= 3.31.0 required for generated columns, got {sqlite3.sqlite_version}"
)


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Required
    API_KEY: str

    # Database
    DB_PATH: str = "/var/lib/waggle/waggle.db"

    # MQTT
    MQTT_HOST: str = "127.0.0.1"
    MQTT_PORT: int = 1883

    # API
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    TRUST_PROXY: bool = False
    STATUS_AUTH: bool = False
    CORS_ORIGIN: str | None = None
    RATE_LIMIT: str = "100/minute"

    # Serial
    SERIAL_DEVICE: str = "/dev/ttyUSB0"
    SERIAL_BAUD: int = 115200

    # Timing
    WAKE_INTERVAL_SEC: int = 60
    MAX_PAST_SKEW_HOURS: int = 72
    MIN_VALID_YEAR: int = 2025

    # Dashboard auth (optional)
    DASHBOARD_AUTH_USER: str | None = None
    DASHBOARD_AUTH_PASS: str | None = None

    @property
    def DB_URL(self) -> str:  # noqa: N802
        return f"sqlite+aiosqlite:///{self.DB_PATH}"

    @model_validator(mode="after")
    def validate_trust_proxy(self) -> "Settings":
        if self.TRUST_PROXY and self.API_HOST != "127.0.0.1":
            raise ValueError(
                "TRUST_PROXY=true requires API_HOST=127.0.0.1 "
                "(only local proxy can set trusted headers)"
            )
        return self
