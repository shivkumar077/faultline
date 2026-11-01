import asyncio
import json
import logging
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.core.config import Settings
from app.core.git_environment import isolated_git_environment
from app.core.logging_config import JsonLogFormatter, configure_logging, request_id_context
from app.core.middleware import FaultlineSecurityMiddleware
from app.main import general_exception_handler
from app.schemas.repair_evaluation import ForgeFitScenarioRequest
from app.schemas.repository_connection import RepositoryRegistrationRequest


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "ENVIRONMENT": "production",
        "DEBUG": False,
        "PRIVATE_DEPLOYMENT": True,
        "DATABASE_URL": "postgresql+psycopg2://faultline:strong-password@postgres/faultline",
        "API_AUTH_TOKEN": "A" * 48,
        "CORS_ORIGINS": [],
        "TRUSTED_HOSTS": ["backend", "localhost"],
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _security_config(**overrides: object) -> SimpleNamespace:
    config = SimpleNamespace(
        ENVIRONMENT="production",
        API_AUTH_TOKEN=SecretStr("A" * 48),
        MAX_REQUEST_BODY_BYTES=8,
        RATE_LIMIT_REQUESTS_PER_MINUTE=2,
        EXPENSIVE_RATE_LIMIT_REQUESTS_PER_MINUTE=1,
        RATE_LIMIT_WINDOW_SECONDS=60,
    )
    config.__dict__.update(overrides)
    return config


def _security_client(**overrides: object) -> TestClient:
    app = FastAPI()

    @app.get("/resource")
    async def get_resource():
        return {"ok": True}

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    @app.post("/api/v1/analyses/{analysis_id}/execute")
    async def execute(analysis_id: str, request: Request):
        return {"analysis_id": analysis_id, "body": (await request.body()).decode()}

    return TestClient(FaultlineSecurityMiddleware(app, _security_config(**overrides)))


def test_production_settings_require_private_auth_and_postgresql():
    settings = _production_settings()
    assert settings.ENVIRONMENT == "production"
    assert settings.DATABASE_URL.get_secret_value().startswith("postgresql+psycopg2://")
    assert "A" * 48 not in repr(settings)


@pytest.mark.parametrize(
    "overrides",
    [
        {"DEBUG": True},
        {"DB_ECHO": True},
        {"LOG_LEVEL": "DEBUG"},
        {"PRIVATE_DEPLOYMENT": False},
        {"API_AUTH_TOKEN": None},
        {"API_AUTH_TOKEN": "weak"},
        {"DATABASE_URL": "sqlite:///./faultline.db"},
        {"CORS_ORIGINS": ["http://example.test"]},
        {"TRUSTED_HOSTS": ["*"]},
        {"TRUSTED_HOSTS": ["*.example.test"]},
    ],
)
def test_production_settings_reject_unsafe_configuration(overrides: dict[str, object]):
    with pytest.raises(ValidationError):
        _production_settings(**overrides)


def test_production_settings_read_database_and_authentication_secrets_from_files(tmp_path):
    database_url_file = tmp_path / "database-url"
    database_url_file.write_text(
        "postgresql://faultline:secret@postgres/faultline",
        encoding="utf-8",
    )
    token_file = tmp_path / "api-token"
    token_file.write_text("B" * 48, encoding="utf-8")
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        DEBUG=False,
        PRIVATE_DEPLOYMENT=True,
        DATABASE_URL_FILE=database_url_file,
        API_AUTH_TOKEN_FILE=token_file,
        CORS_ORIGINS=[],
        TRUSTED_HOSTS=["backend"],
    )

    assert settings.DATABASE_URL.get_secret_value().startswith("postgresql+psycopg2://faultline:")
    assert settings.DATABASE_URL.get_secret_value().endswith("@postgres/faultline")
    assert settings.API_AUTH_TOKEN is not None
    assert settings.API_AUTH_TOKEN.get_secret_value() == "B" * 48
    assert "secret" not in repr(settings)
    assert "B" * 48 not in repr(settings)


def test_settings_load_production_environment_and_json_allowlists(tmp_path, monkeypatch):
    database_url_file = tmp_path / "database-url"
    database_url_file.write_text(
        "postgresql://faultline:db-password@postgres/faultline",
        encoding="utf-8",
    )
    token_file = tmp_path / "api-token"
    token_file.write_text("C" * 48, encoding="utf-8")
    environment = {
        "ENVIRONMENT": "production",
        "DEBUG": "false",
        "PRIVATE_DEPLOYMENT": "true",
        "DATABASE_URL_FILE": str(database_url_file),
        "API_AUTH_TOKEN_FILE": str(token_file),
        "CORS_ORIGINS": "[]",
        "TRUSTED_HOSTS": '["backend","localhost"]',
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)

    settings = Settings(_env_file=None)
    assert settings.ENVIRONMENT == "production"
    assert settings.CORS_ORIGINS == []
    assert settings.TRUSTED_HOSTS == ["backend", "localhost"]
    assert settings.API_AUTH_TOKEN is not None
    assert settings.API_AUTH_TOKEN.get_secret_value() == "C" * 48


def test_production_settings_reject_credentials_in_cors_origin():
    with pytest.raises(ValidationError):
        _production_settings(CORS_ORIGINS=["https://user:password@example.com"])


def test_git_environment_disables_host_git_configuration(monkeypatch):
    monkeypatch.setenv("GIT_TRACE", "1")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "filter.test.smudge")
    environment = isolated_git_environment()

    assert environment["GIT_ALLOW_PROTOCOL"] == "https"
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_TERMINAL_PROMPT"] == "0"
    assert environment["GIT_CONFIG_GLOBAL"]
    assert not any(key.startswith("GIT_TRACE") for key in environment)
    assert "GIT_CONFIG_COUNT" not in environment
    assert "GIT_CONFIG_KEY_0" not in environment


def test_production_authentication_rejects_missing_or_invalid_tokens():
    client = _security_client()
    unauthorized = client.get("/resource")
    assert unauthorized.status_code == 401
    assert unauthorized.json()["error_code"] == "AUTHENTICATION_REQUIRED"
    assert unauthorized.headers["x-request-id"]
    assert unauthorized.headers["cache-control"] == "no-store"
    assert unauthorized.headers["x-content-type-options"] == "nosniff"

    assert (
        client.get("/resource", headers={"Authorization": f"Bearer {'A' * 48}"}).status_code == 200
    )
    assert client.get("/health").status_code == 200


def test_cors_headers_wrap_authentication_errors():
    app = FastAPI()

    @app.get("/resource")
    async def get_resource():
        return {"ok": True}

    app.add_middleware(FaultlineSecurityMiddleware, config=_security_config())
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://ui.example"],
        allow_methods=["GET"],
        allow_headers=["Authorization"],
    )
    response = TestClient(app).get("/resource", headers={"Origin": "https://ui.example"})

    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == "https://ui.example"


def test_request_size_limit_and_expensive_endpoint_rate_limit():
    auth = {"Authorization": f"Bearer {'A' * 48}"}

    oversized = _security_client().post(
        "/api/v1/analyses/analysis-1/execute",
        content=b"123456789",
        headers=auth,
    )
    assert oversized.status_code == 413
    assert oversized.json()["error_code"] == "REQUEST_TOO_LARGE"

    client = _security_client()
    first = client.post(
        "/api/v1/analyses/analysis-1/execute",
        content=b"12345678",
        headers=auth,
    )
    limited = client.post(
        "/api/v1/analyses/analysis-1/execute",
        content=b"12345678",
        headers=auth,
    )
    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.headers["retry-after"]
    assert limited.json()["error_code"] == "RATE_LIMITED"


def test_request_id_is_validated_and_returned():
    client = _security_client()
    response = client.get(
        "/resource",
        headers={
            "Authorization": f"Bearer {'A' * 48}",
            "X-Request-ID": "trace-2026.1",
        },
    )
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "trace-2026.1"

    invalid = client.get(
        "/resource",
        headers={
            "Authorization": f"Bearer {'A' * 48}",
            "X-Request-ID": "invalid request id",
        },
    )
    assert invalid.status_code == 200
    assert invalid.headers["x-request-id"] != "invalid request id"


def test_structured_logging_includes_correlation_but_not_exception_details():
    record = logging.LogRecord(
        "faultline.test",
        logging.INFO,
        "test.py",
        1,
        "request_complete",
        (),
        None,
    )
    context_token = request_id_context.set("trace-id")
    try:
        formatted = JsonLogFormatter().format(record)
    finally:
        request_id_context.reset(context_token)
    parsed = json.loads(formatted)
    assert parsed["message"] == "request_complete"
    assert parsed["request_id"] == "trace-id"


def test_application_loggers_use_structured_json_format():
    configure_logging("INFO")
    for logger_name in ("app", "faultline"):
        logger = logging.getLogger(logger_name)
        assert logger.handlers
        assert all(isinstance(handler.formatter, JsonLogFormatter) for handler in logger.handlers)


def test_unhandled_error_response_does_not_echo_exception_or_traceback():
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/resource",
            "raw_path": b"/resource",
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "state": {"request_id": "trace-id"},
        }
    )
    response: JSONResponse = asyncio.run(
        general_exception_handler(request, RuntimeError("sensitive source and secret"))
    )
    body = json.loads(response.body)
    assert response.status_code == 500
    assert "sensitive source and secret" not in response.body.decode()
    assert body["request_id"] == "trace-id"


@pytest.mark.parametrize("branch", ["--help", "../main", "release..x", "feature/name.lock"])
def test_repository_registration_rejects_invalid_git_branch_names(branch: str):
    with pytest.raises(ValidationError):
        RepositoryRegistrationRequest(
            repository_url="https://github.com/acme/project",
            branch=branch,
        )


@pytest.mark.parametrize(
    "target_url",
    [
        "http://169.254.169.254/latest/meta-data",
        "http://192.168.1.1/admin",
        "http://metadata.google.internal/",
        "https://user:password@example.com/",
        "https://example.com/path#fragment",
    ],
)
def test_forgefit_scenario_rejects_private_or_credentialed_urls(target_url: str):
    with pytest.raises(ValidationError):
        ForgeFitScenarioRequest(target_url=target_url)
