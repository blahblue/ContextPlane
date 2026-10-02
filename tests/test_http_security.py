import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from contextplane.app import app
from contextplane.context_registry.domain import ContextDomain
from contextplane.http_security import HttpPerimeterMiddleware
from contextplane.runtime import ResolveContextRequest


def test_security_headers_are_present_on_health() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["content-security-policy"].startswith("default-src 'none'")


def test_sensitive_api_responses_are_not_shared_cacheable() -> None:
    response = TestClient(app).post(
        "/v1/context/resolve",
        json={"domains": ["engineering"]},
    )

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"


def test_hsts_is_emitted_only_for_https_requests() -> None:
    https_response = TestClient(app, base_url="https://testserver").get("/health")
    http_response = TestClient(app, base_url="http://testserver").get("/health")

    assert "strict-transport-security" in https_response.headers
    assert "strict-transport-security" not in http_response.headers


def test_api_docs_are_disabled_by_default() -> None:
    client = TestClient(app)

    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_reference_rate_limiter_blocks_after_configured_limit() -> None:
    isolated = FastAPI()

    @isolated.get("/v1/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    isolated.add_middleware(
        HttpPerimeterMiddleware,
        requests_per_minute=2,
        max_tracked_clients=100,
    )
    client = TestClient(isolated)

    assert client.get("/v1/ping").status_code == 200
    assert client.get("/v1/ping").status_code == 200
    limited = client.get("/v1/ping")

    assert limited.status_code == 429
    assert limited.headers["retry-after"] == "60"
    assert limited.headers["cache-control"] == "no-store, private"


def test_resolve_key_filter_is_count_bounded() -> None:
    with pytest.raises(ValidationError):
        ResolveContextRequest(
            domains=frozenset({ContextDomain.ENGINEERING}),
            keys=frozenset(f"engineering.key.{index}" for index in range(101)),
        )
