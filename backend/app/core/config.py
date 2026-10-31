from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    APP_NAME: str = "FAULTLINE"
    APP_VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        return []

    # Database
    DATABASE_URL: str = "postgresql://faultline:faultline_dev_secret@localhost:5432/faultline"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False

    # Optional ForgeFit resilience API integration
    FORGEFIT_BASE_URL: str | None = None
    FORGEFIT_API_KEY: str | None = None
    FORGEFIT_TIMEOUT_SECONDS: int = 5
    FORGEFIT_MAX_WAIT_SECONDS: int = 300
    FORGEFIT_POLL_INTERVAL_SECONDS: int = 1

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def assemble_database_url(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+psycopg2://", 1)
        return v

    @field_validator(
        "FORGEFIT_TIMEOUT_SECONDS",
        "FORGEFIT_MAX_WAIT_SECONDS",
        "FORGEFIT_POLL_INTERVAL_SECONDS",
    )
    @classmethod
    def validate_forgefit_timeouts(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("ForgeFit timeout settings must be positive.")
        return value


settings = Settings()
