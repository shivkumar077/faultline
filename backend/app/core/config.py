import ipaddress
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{32,512}$")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PRIVATE_DEPLOYMENT: bool = False
    APP_NAME: str = "FAULTLINE"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    LOG_LEVEL: str = "INFO"

    CORS_ORIGINS: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8000",
        ]
    )
    TRUSTED_HOSTS: list[str] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "backend"]
    )

    API_AUTH_TOKEN: SecretStr | None = Field(default=None, repr=False)
    API_AUTH_TOKEN_FILE: Path | None = Field(default=None, repr=False)
    MAX_REQUEST_BODY_BYTES: int = Field(default=1_048_576, gt=0, le=16_777_216)
    RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=120, ge=1, le=10_000)
    EXPENSIVE_RATE_LIMIT_REQUESTS_PER_MINUTE: int = Field(default=10, ge=1, le=1_000)
    RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3600)

    DATABASE_URL: SecretStr = Field(
        default=SecretStr("sqlite:///./db.sqlite3"),
        repr=False,
    )
    DATABASE_URL_FILE: Path | None = Field(default=None, repr=False)
    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=500)
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1, le=600)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=1, le=86_400)
    DB_CONNECT_TIMEOUT_SECONDS: int = Field(default=5, ge=1, le=120)
    DB_STATEMENT_TIMEOUT_MS: int = Field(default=30_000, ge=1, le=3_600_000)
    DB_LOCK_TIMEOUT_MS: int = Field(default=5_000, ge=1, le=600_000)
    DB_ECHO: bool = False

    FORGEFIT_BASE_URL: str | None = None
    FORGEFIT_ALLOW_EXTERNAL_TARGETS: bool = False
    FORGEFIT_API_KEY: SecretStr | None = Field(default=None, repr=False)
    FORGEFIT_API_KEY_FILE: Path | None = Field(default=None, repr=False)
    FORGEFIT_TIMEOUT_SECONDS: int = Field(default=5, ge=1, le=120)
    FORGEFIT_MAX_WAIT_SECONDS: int = Field(default=300, ge=1, le=3600)
    FORGEFIT_POLL_INTERVAL_SECONDS: int = Field(default=1, ge=1, le=60)

    @field_validator("ENVIRONMENT", mode="before")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("CORS_ORIGINS", "TRUSTED_HOSTS", mode="before")
    @classmethod
    def assemble_string_lists(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                if not isinstance(parsed, list) or not all(
                    isinstance(item, str) for item in parsed
                ):
                    raise ValueError("Expected a JSON array of strings.")
                return parsed
            return [item.strip() for item in stripped.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        raise ValueError("Expected a list of strings.")

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str | SecretStr) -> str:
        if isinstance(value, SecretStr):
            value = value.get_secret_value()
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg2://", 1)
        return value

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL must be a standard Python logging level.")
        return normalized

    @field_validator("FORGEFIT_BASE_URL")
    @classmethod
    def validate_forgefit_base_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        try:
            parsed = urlsplit(value.strip())
            _ = parsed.port
        except ValueError:
            raise ValueError("FORGEFIT_BASE_URL must be a valid absolute URL.") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("FORGEFIT_BASE_URL must not contain credentials or URL parameters.")
        if parsed.scheme != "https":
            hostname = parsed.hostname.casefold()
            try:
                loopback = ipaddress.ip_address(hostname).is_loopback
            except ValueError:
                loopback = hostname == "localhost"
            if not loopback:
                raise ValueError("Non-loopback ForgeFit endpoints must use HTTPS.")
        return value.strip().rstrip("/")

    @model_validator(mode="after")
    def validate_deployment(self) -> "Settings":
        if self.ENVIRONMENT not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, or production.")

        for field_name in ("API_AUTH_TOKEN", "FORGEFIT_API_KEY"):
            secret = getattr(self, field_name)
            if secret is not None and not secret.get_secret_value().strip():
                setattr(self, field_name, None)

        if self.DATABASE_URL_FILE is not None:
            if "DATABASE_URL" in self.model_fields_set:
                raise ValueError("Set DATABASE_URL or DATABASE_URL_FILE, not both.")
            try:
                database_url = self.DATABASE_URL_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                raise ValueError(
                    "The configured database URL secret file cannot be read."
                ) from None
            self.DATABASE_URL = SecretStr(self.normalize_database_url(database_url))

        if self.FORGEFIT_API_KEY_FILE is not None:
            if self.FORGEFIT_API_KEY is not None:
                raise ValueError("Set FORGEFIT_API_KEY or FORGEFIT_API_KEY_FILE, not both.")
            try:
                forgefit_api_key = self.FORGEFIT_API_KEY_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                raise ValueError("The configured ForgeFit API key file cannot be read.") from None
            if not forgefit_api_key:
                raise ValueError("The configured ForgeFit API key file is empty.")
            self.FORGEFIT_API_KEY = SecretStr(forgefit_api_key)

        if self.API_AUTH_TOKEN_FILE is not None:
            if self.API_AUTH_TOKEN is not None:
                raise ValueError("Set API_AUTH_TOKEN or API_AUTH_TOKEN_FILE, not both.")
            try:
                self.API_AUTH_TOKEN = SecretStr(
                    self.API_AUTH_TOKEN_FILE.read_text(encoding="utf-8").strip()
                )
            except OSError:
                raise ValueError("The configured API token file cannot be read.") from None

        if self.API_AUTH_TOKEN is not None and not _TOKEN_PATTERN.fullmatch(
            self.API_AUTH_TOKEN.get_secret_value()
        ):
            raise ValueError("API_AUTH_TOKEN must be at least 32 URL-safe characters.")

        if self.ENVIRONMENT == "production":
            try:
                database_url = urlsplit(self.DATABASE_URL.get_secret_value())
                _ = database_url.port
            except ValueError:
                raise ValueError("DATABASE_URL must be a valid PostgreSQL URL.") from None
            if (
                "DATABASE_URL" not in self.model_fields_set
                and "DATABASE_URL_FILE" not in self.model_fields_set
            ):
                raise ValueError("Production requires an explicit DATABASE_URL or secret file.")
            if database_url.scheme != "postgresql+psycopg2" or not database_url.hostname:
                raise ValueError("Production DATABASE_URL must target PostgreSQL.")
            if self.DEBUG or not self.PRIVATE_DEPLOYMENT:
                raise ValueError("Production requires DEBUG=false and PRIVATE_DEPLOYMENT=true.")
            if self.DB_ECHO or self.LOG_LEVEL == "DEBUG":
                raise ValueError("Production requires DB_ECHO=false and a non-debug log level.")
            if self.API_AUTH_TOKEN is None:
                raise ValueError("Production requires a configured API authentication token.")
            if not self.TRUSTED_HOSTS or any(
                "*" in host or "://" in host or not host.strip() or host != host.strip()
                for host in self.TRUSTED_HOSTS
            ):
                raise ValueError("Production requires an explicit trusted-host allowlist.")
            for origin in self.CORS_ORIGINS:
                try:
                    parsed_origin = urlsplit(origin)
                    _ = parsed_origin.port
                except ValueError:
                    raise ValueError(
                        "Production CORS origins must be valid HTTPS origins."
                    ) from None
                if (
                    parsed_origin.scheme != "https"
                    or not parsed_origin.hostname
                    or parsed_origin.username
                    or parsed_origin.password
                    or parsed_origin.path not in {"", "/"}
                    or parsed_origin.query
                    or parsed_origin.fragment
                ):
                    raise ValueError("Production CORS origins must be explicit HTTPS origins.")

        return self


settings = Settings()
