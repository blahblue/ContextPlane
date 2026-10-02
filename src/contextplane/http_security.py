"""HTTP perimeter hardening for the reference REST service."""

from __future__ import annotations

import hashlib
import os
import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from fastapi import Request, Response, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean")


def _int_env(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class HttpPerimeterConfig:
    """Process-local HTTP perimeter configuration."""

    expose_api_docs: bool = False
    requests_per_minute: int = 120
    max_tracked_clients: int = 10_000

    @classmethod
    def from_environment(cls) -> HttpPerimeterConfig:
        """Read bounded REST-perimeter controls from environment variables."""
        return cls(
            expose_api_docs=_bool_env("CONTEXTPLANE_EXPOSE_API_DOCS", False),
            requests_per_minute=_int_env(
                "CONTEXTPLANE_HTTP_RATE_LIMIT_PER_MINUTE",
                120,
                minimum=1,
                maximum=100_000,
            ),
            max_tracked_clients=_int_env(
                "CONTEXTPLANE_HTTP_RATE_LIMIT_MAX_CLIENTS",
                10_000,
                minimum=100,
                maximum=1_000_000,
            ),
        )


class InMemoryFixedWindowLimiter:
    """Bounded process-local fixed-window limiter keyed by direct peer address."""

    def __init__(self, *, requests_per_minute: int, max_clients: int) -> None:
        self._limit = requests_per_minute
        self._max_clients = max_clients
        self._entries: OrderedDict[str, tuple[int, int]] = OrderedDict()
        self._lock = Lock()

    def allow(self, key: str, *, now: float | None = None) -> bool:
        """Return whether one request is allowed in the current minute window."""
        minute = int((time.time() if now is None else now) // 60)
        with self._lock:
            existing = self._entries.pop(key, None)
            if existing is None or existing[0] != minute:
                self._entries[key] = (minute, 1)
                while len(self._entries) > self._max_clients:
                    self._entries.popitem(last=False)
                return True

            _, count = existing
            next_count = count + 1
            self._entries[key] = (minute, next_count)
            return next_count <= self._limit


class HttpPerimeterMiddleware(BaseHTTPMiddleware):
    """Apply rate limiting, security headers, and private-cache policy."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        requests_per_minute: int,
        max_tracked_clients: int,
    ) -> None:
        super().__init__(app)
        self._limiter = InMemoryFixedWindowLimiter(
            requests_per_minute=requests_per_minute,
            max_clients=max_tracked_clients,
        )

    @staticmethod
    def _client_key(request: Request) -> str:
        direct_host = request.client.host if request.client is not None else "unknown"
        # Hash rather than retain raw peer values in process memory.
        return hashlib.sha256(direct_host.encode("utf-8")).hexdigest()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith("/v1/"):
            if not self._limiter.allow(self._client_key(request)):
                response = Response(
                    content='{"detail":"rate limit exceeded"}',
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    media_type="application/json",
                    headers={"Retry-After": "60"},
                )
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )

        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        if request.url.path.startswith("/v1/"):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Pragma"] = "no-cache"

        return response
