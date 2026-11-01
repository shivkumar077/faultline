import asyncio
import hmac
import json
import logging
import math
import re
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import Settings
from app.core.logging_config import request_id_context

ASGIMessage = dict[str, Any]
ASGIReceive = Callable[[], Awaitable[ASGIMessage]]
ASGISend = Callable[[ASGIMessage], Awaitable[None]]
ASGIApp = Callable[[dict[str, Any], ASGIReceive, ASGISend], Awaitable[None]]
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_HEALTH_PATHS = {
    "/health",
    "/health/live",
    "/health/ready",
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
}
_EXPENSIVE_PATH_SEGMENTS = {
    "sync",
    "mutations",
    "execute",
    "diagnose",
    "repair-candidates",
    "evaluations",
}
_MAX_RATE_LIMIT_ENTRIES = 4096


class FaultlineSecurityMiddleware:
    """Enforce production API authentication, bounded requests, and process-local limits."""

    def __init__(self, app: ASGIApp, config: Settings):
        self.app = app
        self.config = config
        self._limits: OrderedDict[str, tuple[float, int]] = OrderedDict()
        self._limits_lock = asyncio.Lock()

    async def __call__(self, scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {
            key.lower(): value
            for key, value in scope.get("headers", [])
            if isinstance(key, bytes) and isinstance(value, bytes)
        }
        authorization_values = [
            value
            for key, value in scope.get("headers", [])
            if isinstance(key, bytes) and key.lower() == b"authorization"
        ]
        raw_request_id = headers.get(b"x-request-id", b"").decode("ascii", errors="ignore")
        request_id = (
            raw_request_id if _REQUEST_ID_PATTERN.fullmatch(raw_request_id) else uuid.uuid4().hex
        )
        scope.setdefault("state", {})["request_id"] = request_id
        context_token = request_id_context.set(request_id)
        status_code = 500
        started = time.monotonic()
        method = scope.get("method", "GET").upper()
        path = scope.get("path", "/")

        async def send_with_request_id(message: ASGIMessage) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                protected_headers = {
                    b"x-request-id",
                    b"x-content-type-options",
                    b"cache-control",
                }
                response_headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in protected_headers
                ]
                response_headers.append((b"x-request-id", request_id.encode("ascii")))
                response_headers.append((b"x-content-type-options", b"nosniff"))
                response_headers.append((b"cache-control", b"no-store"))
                message["headers"] = response_headers
            await send(message)

        try:
            if (
                self.config.ENVIRONMENT == "production"
                and path not in _HEALTH_PATHS
                and method != "OPTIONS"
                and not self._authorized(authorization_values)
            ):
                await self._respond(
                    send_with_request_id,
                    401,
                    "Authentication is required.",
                    "AUTHENTICATION_REQUIRED",
                    request_id=request_id,
                    extra_headers=[(b"www-authenticate", b"Bearer")],
                )
                return

            if (
                self.config.ENVIRONMENT == "production"
                and method != "OPTIONS"
                and path not in _HEALTH_PATHS
            ):
                client = scope.get("client")
                client_host = str(client[0]) if client else "unknown"
                limit = (
                    self.config.EXPENSIVE_RATE_LIMIT_REQUESTS_PER_MINUTE
                    if self._is_expensive(path)
                    else self.config.RATE_LIMIT_REQUESTS_PER_MINUTE
                )
                allowed, retry_after = await self._consume_rate_limit(
                    f"{client_host}:{self._rate_group(method, path)}",
                    limit,
                    self.config.RATE_LIMIT_WINDOW_SECONDS,
                )
                if not allowed:
                    await self._respond(
                        send_with_request_id,
                        429,
                        "Request rate limit exceeded.",
                        "RATE_LIMITED",
                        request_id=request_id,
                        extra_headers=[(b"retry-after", str(retry_after).encode("ascii"))],
                    )
                    return

            body = await self._read_bounded_body(headers, receive)
            if body is None:
                await self._respond(
                    send_with_request_id,
                    413,
                    "Request body exceeds the configured size limit.",
                    "REQUEST_TOO_LARGE",
                    request_id=request_id,
                )
                return
            if body is False:
                await self._respond(
                    send_with_request_id,
                    400,
                    "Invalid request content length.",
                    "INVALID_CONTENT_LENGTH",
                    request_id=request_id,
                )
                return

            body_sent = False

            async def replay_receive() -> ASGIMessage:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, replay_receive, send_with_request_id)
        finally:
            logging.getLogger("faultline.http").info(
                "http_request",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                },
            )
            request_id_context.reset(context_token)

    def _authorized(self, authorization_values: list[bytes]) -> bool:
        token = self.config.API_AUTH_TOKEN
        if token is None or len(authorization_values) != 1:
            return False
        try:
            value = authorization_values[0].decode("ascii")
        except UnicodeDecodeError:
            return False
        scheme, separator, supplied_token = value.partition(" ")
        return (
            separator == " "
            and scheme.casefold() == "bearer"
            and bool(supplied_token)
            and len(supplied_token) <= 512
            and hmac.compare_digest(token.get_secret_value(), supplied_token)
        )

    @staticmethod
    def _is_expensive(path: str) -> bool:
        return bool(_EXPENSIVE_PATH_SEGMENTS.intersection(path.casefold().split("/")))

    @staticmethod
    def _rate_group(method: str, path: str) -> str:
        return f"expensive:{method}" if FaultlineSecurityMiddleware._is_expensive(path) else method

    async def _consume_rate_limit(
        self, key: str, limit: int, window_seconds: int
    ) -> tuple[bool, int]:
        now = time.monotonic()
        async with self._limits_lock:
            current = self._limits.get(key)
            if current is None or now - current[0] >= window_seconds:
                self._limits[key] = (now, 1)
                self._limits.move_to_end(key)
                while len(self._limits) > _MAX_RATE_LIMIT_ENTRIES:
                    self._limits.popitem(last=False)
                return True, 0
            window_started, count = current
            retry_after = max(1, math.ceil(window_seconds - (now - window_started)))
            if count >= limit:
                self._limits.move_to_end(key)
                return False, retry_after
            self._limits[key] = (window_started, count + 1)
            self._limits.move_to_end(key)
            return True, 0

    async def _read_bounded_body(
        self, headers: dict[bytes, bytes], receive: ASGIReceive
    ) -> bytes | None | bool:
        try:
            content_length = headers.get(b"content-length")
            if content_length is not None:
                declared_size = int(content_length)
                if declared_size < 0:
                    return False
                if declared_size > self.config.MAX_REQUEST_BODY_BYTES:
                    return None
        except ValueError:
            return False

        content = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return bytes(content)
            if message["type"] != "http.request":
                continue
            content.extend(message.get("body", b""))
            if len(content) > self.config.MAX_REQUEST_BODY_BYTES:
                return None
            if not message.get("more_body", False):
                return bytes(content)

    @staticmethod
    async def _respond(
        send: ASGISend,
        status_code: int,
        detail: str,
        error_code: str,
        *,
        request_id: str,
        extra_headers: list[tuple[bytes, bytes]] | None = None,
    ) -> None:
        body = json.dumps(
            {
                "detail": detail,
                "error_code": error_code,
                "extra": {},
                "request_id": request_id,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        headers = [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
        if extra_headers:
            headers.extend(extra_headers)
        await send({"type": "http.response.start", "status": status_code, "headers": headers})
        await send({"type": "http.response.body", "body": body})
