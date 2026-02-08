"""Application configuration via pydantic-settings."""

import sqlite3

from pydantic import field_validator, model_validator
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

    # Phase 3 — Camera & ML
    ADMIN_API_KEY: str | None = None
    MAX_QUEUE_DEPTH: int = 50
    DISK_USAGE_THRESHOLD: float = 0.90
    MAX_PHOTO_SIZE: int = 204800  # 200 KB
    PHOTO_DIR: str = "/var/lib/waggle/photos"
    PHOTO_RETENTION_DAYS: int = 30
    EXPECTED_MODEL_HASH: str | None = None
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.25

    # Phase 3 — Cloud Sync (Supabase)
    SUPABASE_URL: str | None = None
    SUPABASE_SERVICE_KEY: str | None = None
    SYNC_INTERVAL_SEC: int = 300

    # Phase 3 — Webhooks
    WEBHOOK_URLS: list[str] = []
    WEBHOOK_SECRET: str = ""

    # Phase 3 — Weather
    WEATHER_PROVIDER: str = "none"
    OPENWEATHERMAP_API_KEY: str = ""
    WEATHER_LATITUDE: str = ""
    WEATHER_LONGITUDE: str = ""

    # Phase 3 — Local image signing
    FASTAPI_BASE_URL: str = "http://localhost:8000"
    LOCAL_SIGNING_SECRET: str | None = None
    LOCAL_SIGNING_TTL_SEC: int = 600

    # Phase 3 — Dashboard (local mode)
    PI_API_KEY: str | None = None
    PI_API_URL: str = "http://localhost:8000"

    @field_validator("WEBHOOK_URLS", mode="before")
    @classmethod
    def parse_webhook_urls(cls, v: object) -> object:
        if isinstance(v, str):
            return [u.strip() for u in v.split(",") if u.strip()]
        return v

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

    @model_validator(mode="after")
    def validate_weather_provider(self) -> "Settings":
        if self.WEATHER_PROVIDER == "owm":
            self.WEATHER_PROVIDER = "openweathermap"
        if self.WEATHER_PROVIDER not in ("openweathermap", "bom", "none"):
            raise ValueError(
                f"WEATHER_PROVIDER must be one of 'openweathermap', 'bom', 'none', "
                f"got '{self.WEATHER_PROVIDER}'"
            )
        return self
