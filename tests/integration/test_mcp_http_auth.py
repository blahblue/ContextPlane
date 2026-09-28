import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.settings import AuthSettings
from pydantic import AnyHttpUrl
from sqlalchemy.orm import Session

from contextplane.auth import EntraValidatorConfig, StaticKeyEntraValidator
from contextplane.cache import InMemoryResolutionCache
from contextplane.context_registry import (
    AuthorityLevel,
    ContextDomain,
    ContextItemCreate,
    ContextScope,
    ContextSource,
    OverridePolicy,
    SensitivityLevel,
    SourceType,
)
from contextplane.context_registry.repository import create_context_item
from contextplane.database import build_engine
from contextplane.mcp import ContextPlaneEntraTokenVerifier, build_mcp_server
from contextplane.settings import Settings

pytestmark = pytest.mark.integration

TENANT = "11111111-2222-3333-4444-555555555555"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
AUDIENCE = "api://contextplane"
RESOURCE_URL = "http://127.0.0.1:8000/mcp"
NOW = datetime.now(UTC)


@pytest.fixture(scope="module")
def keypair() -> tuple[str, str]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


@pytest.fixture
def engine():
    db_engine = build_engine(Settings())
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def claims(*, oid: str, scopes: str | None = "context.resolve") -> dict[str, Any]:
    now = datetime.now(UTC)
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "tid": TENANT,
        "oid": oid,
        "azp": "99999999-8888-7777-6666-555555555555",
        "scp": scopes,
    }


def encode(private_key: str, payload: dict[str, Any]) -> str:
    return jwt.encode(payload, private_key, algorithm="RS256")


def context_item(*, subject: str) -> ContextItemCreate:
    return ContextItemCreate(
        key="engineering.http-auth",
        value={"value": "authenticated-http"},
        domain=ContextDomain.ENGINEERING,
        scope=ContextScope(tenant_id=TENANT, user_id=subject),
        owner="mcp-http-test",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"mcp-http-{subject}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=NOW - timedelta(days=1),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum="a" * 64,
    )


def server_for(engine, public_key: str):
    verifier = ContextPlaneEntraTokenVerifier(
        StaticKeyEntraValidator(
            EntraValidatorConfig(
                tenant_id=TENANT,
                issuer=ISSUER,
                audience=AUDIENCE,
                public_key_pem=public_key,
                clock_skew_seconds=0,
            )
        )
    )
    return build_mcp_server(
        engine=engine,
        cache=InMemoryResolutionCache(ttl_seconds=60, max_entries=16),
        rules_provider=tuple,
        token_verifier=verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(ISSUER),
            resource_server_url=AnyHttpUrl(RESOURCE_URL),
            required_scopes=["context.resolve"],
            validate_token_resource=False,
        ),
    )


def test_streamable_http_rejects_missing_and_insufficient_bearer(
    engine,
    keypair: tuple[str, str],
) -> None:
    private_key, public_key = keypair
    server = server_for(engine, public_key)
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="127.0.0.1",
    )

    async def exercise() -> None:
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(
            transport=transport,
            base_url="http://127.0.0.1:8000",
        ) as client:
            missing = await client.post("/mcp", json={})
            insufficient = await client.post(
                "/mcp",
                json={},
                headers={
                    "Authorization": (
                        "Bearer "
                        + encode(
                            private_key,
                            claims(
                                oid="bbbbbbbb-cccc-dddd-eeee-ffffffffffff",
                                scopes="context.read",
                            ),
                        )
                    )
                },
            )

        assert missing.status_code == 401
        assert insufficient.status_code == 401
        assert missing.json()["error"] == "invalid_token"
        assert insufficient.json()["error"] == "invalid_token"

    asyncio.run(exercise())


def test_streamable_http_valid_bearer_reaches_tool_as_authenticated_principal(
    engine,
    keypair: tuple[str, str],
) -> None:
    private_key, public_key = keypair
    subject = f"mcp-http-{uuid4()}"

    with Session(engine) as session:
        create_context_item(session, context_item(subject=subject))
        session.commit()

    server = server_for(engine, public_key)
    app = server.streamable_http_app(
        stateless_http=True,
        json_response=True,
        host="127.0.0.1",
    )
    token = encode(private_key, claims(oid=subject))

    async def exercise() -> None:
        url = RESOURCE_URL
        transport = httpx2.ASGITransport(app=app)
        headers = {"Authorization": f"Bearer {token}"}

        async with server.session_manager.run():
            async with (
                httpx2.AsyncClient(
                    transport=transport,
                    base_url=url,
                    headers=headers,
                ) as http_client,
                Client(
                    streamable_http_client(
                        url,
                        http_client=http_client,
                    )
                ) as client,
            ):
                result = await client.call_tool(
                    "resolve_context",
                    {"domains": ["engineering"]},
                )

        assert result.is_error is False
        assert result.structured_content is not None
        assert result.structured_content["tenant_id"] == TENANT
        assert result.structured_content["context"][0]["key"] == (
            "engineering.http-auth"
        )
        assert result.structured_content["context"][0]["value"] == {
            "value": "authenticated-http"
        }

    asyncio.run(exercise())
