"""Optional adapter for the existing ForgeFit asynchronous run API."""

import ipaddress
import json
import time
import uuid
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from app.core.config import settings
from app.schemas.repair_evaluation import ForgeFitScenarioRequest

_MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_REPORT_FIELDS = (
    "total_requests",
    "successful_requests",
    "failed_requests",
    "simulated_fault_count",
    "http_error_count",
    "timeout_count",
    "connection_error_count",
    "average_latency_ms",
    "p95_latency_ms",
    "total_duration_ms",
    "interrupted",
)


class ForgeFitAdapterError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ForgeFitOutcome:
    status: str
    run_id: str | None = None
    result: dict[str, object] | None = None
    error_code: str | None = None


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new_url):
        return None


class ForgeFitAdapter:
    """Submit an explicitly requested resilience scenario to ForgeFit."""

    def run_scenario(
        self,
        scenario: ForgeFitScenarioRequest,
        *,
        candidate_id: uuid.UUID,
        evaluation_id: uuid.UUID,
    ) -> ForgeFitOutcome:
        if not settings.FORGEFIT_BASE_URL:
            return ForgeFitOutcome(status="not_configured", error_code="NOT_CONFIGURED")
        try:
            target = urlsplit(str(scenario.target_url))
            if not _is_loopback(target.hostname) and not (
                scenario.allow_external and scenario.authorized_acknowledgement
            ):
                raise ForgeFitAdapterError("EXTERNAL_TARGET_NOT_AUTHORIZED")
            base_url = self._validated_base_url(settings.FORGEFIT_BASE_URL)
            headers = {"Accept": "application/json"}

            health = self._request_json("GET", f"{base_url}/api/status", headers)
            if health.get("status") != "ok":
                raise ForgeFitAdapterError("HEALTH_CHECK_FAILED")
            if health.get("api_key_required") and not settings.FORGEFIT_API_KEY:
                raise ForgeFitAdapterError("API_KEY_REQUIRED")
            run_headers = dict(headers)
            if health.get("api_key_required") and settings.FORGEFIT_API_KEY:
                run_headers["X-ForgeFit-API-Key"] = settings.FORGEFIT_API_KEY

            run_payload = {
                "scenario": {
                    "name": f"Faultline evaluation {evaluation_id.hex[:12]}",
                    "description": "Optional resilience run requested for a repair evaluation.",
                    "tags": [str(candidate_id), str(evaluation_id)],
                    "config": {
                        "target_url": str(scenario.target_url),
                        "request_count": scenario.request_count,
                        "timeout_seconds": scenario.timeout_seconds,
                        "artificial_latency_ms": scenario.artificial_latency_ms,
                        "failure_probability": scenario.failure_probability,
                        "total_deadline_seconds": scenario.total_deadline_seconds,
                        "allow_external": scenario.allow_external,
                        "authorized_acknowledgement": scenario.authorized_acknowledgement,
                        "seed": scenario.seed,
                    },
                },
                "save_report": False,
            }
            started = self._request_json(
                "POST",
                f"{base_url}/api/runs",
                run_headers,
                payload=run_payload,
            )
            run_id = started.get("run_id")
            if not isinstance(run_id, str) or not run_id or len(run_id) > 128:
                raise ForgeFitAdapterError("INVALID_START_RESPONSE")
            return self._poll_run(base_url, headers, run_id)
        except ForgeFitAdapterError as exc:
            return ForgeFitOutcome(status="error", error_code=exc.code)

    def _poll_run(
        self,
        base_url: str,
        headers: dict[str, str],
        run_id: str,
    ) -> ForgeFitOutcome:
        deadline = time.monotonic() + settings.FORGEFIT_MAX_WAIT_SECONDS
        encoded_id = quote(run_id, safe="")
        while time.monotonic() < deadline:
            state = self._request_json("GET", f"{base_url}/api/runs/{encoded_id}", headers)
            status = state.get("status")
            if status == "completed":
                report = state.get("report")
                if not isinstance(report, dict):
                    raise ForgeFitAdapterError("INVALID_REPORT")
                summary = {
                    key: report[key]
                    for key in _REPORT_FIELDS
                    if key in report and isinstance(report[key], (int, float, bool))
                }
                return ForgeFitOutcome(status="completed", run_id=run_id, result=summary)
            if status == "interrupted":
                return ForgeFitOutcome(
                    status="interrupted",
                    run_id=run_id,
                    error_code="RUN_INTERRUPTED",
                )
            if status == "failed":
                return ForgeFitOutcome(
                    status="failed",
                    run_id=run_id,
                    error_code="RUN_FAILED",
                )
            if status not in {"queued", "running"}:
                raise ForgeFitAdapterError("INVALID_RUN_STATUS")
            time.sleep(
                min(
                    settings.FORGEFIT_POLL_INTERVAL_SECONDS,
                    max(0.0, deadline - time.monotonic()),
                )
            )
        return ForgeFitOutcome(
            status="error",
            run_id=run_id,
            error_code="POLL_TIMEOUT",
        )

    @staticmethod
    def _validated_base_url(raw_url: str) -> str:
        try:
            parsed = urlsplit(raw_url)
            _ = parsed.port
        except ValueError:
            raise ForgeFitAdapterError("INVALID_BASE_URL") from None
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ForgeFitAdapterError("INVALID_BASE_URL")
        if parsed.scheme != "https" and not _is_loopback(parsed.hostname):
            raise ForgeFitAdapterError("INSECURE_BASE_URL")
        if settings.FORGEFIT_API_KEY and any(
            character in settings.FORGEFIT_API_KEY for character in "\r\n"
        ):
            raise ForgeFitAdapterError("INVALID_API_KEY")
        return raw_url.rstrip("/")

    @staticmethod
    def _request_json(
        method: str,
        url: str,
        headers: dict[str, str],
        *,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        data = None
        request_headers = dict(headers)
        if payload is not None:
            data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=request_headers, method=method)
        opener = build_opener(_NoRedirectHandler)
        try:
            with opener.open(request, timeout=settings.FORGEFIT_TIMEOUT_SECONDS) as response:
                body = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            raise ForgeFitAdapterError(f"HTTP_{exc.code}") from None
        except (URLError, TimeoutError, OSError) as exc:
            raise ForgeFitAdapterError(
                "REQUEST_TIMEOUT" if isinstance(exc, TimeoutError) else "CONNECTION_FAILED"
            ) from None
        if len(body) > _MAX_RESPONSE_BYTES:
            raise ForgeFitAdapterError("RESPONSE_TOO_LARGE")
        try:
            decoded = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ForgeFitAdapterError("INVALID_JSON") from None
        if not isinstance(decoded, dict):
            raise ForgeFitAdapterError("INVALID_RESPONSE")
        return decoded


def _is_loopback(hostname: str | None) -> bool:
    if not hostname:
        return False
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


forgefit_adapter = ForgeFitAdapter()
