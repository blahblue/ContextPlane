import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from mcp.server.mcpserver.exceptions import ToolError
from sqlalchemy.orm import Session

from contextplane.auth import Principal, PrincipalKind
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
from contextplane.mcp import build_mcp_server
from contextplane.settings import Settings

pytestmark = pytest.mark.integration
NOW = datetime.now(UTC)


@pytest.fixture
def engine():
    db_engine = build_engine(Settings())
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def principal(tenant_id: str) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        subject="mcp-user",
        kind=PrincipalKind.USER,
        client_id="mcp-client",
        roles=frozenset({"developer"}),
        groups=frozenset({"platform"}),
        scopes=frozenset({"context.resolve"}),
    )


def item(
    *,
    tenant_id: str,
    key: str,
    checksum_char: str,
    value: str,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"value": value},
        domain=ContextDomain.ENGINEERING,
        scope=ContextScope(tenant_id=tenant_id),
        owner="mcp-test-owner",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"{key}-{checksum_char}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=NOW - timedelta(days=1),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum_char * 64,
    )


def build_test_server(engine, tenant_id: str):
    return build_mcp_server(
        engine=engine,
        cache=InMemoryResolutionCache(ttl_seconds=60, max_entries=16),
        rules_provider=tuple,
        principal_provider=lambda: principal(tenant_id),
    )


def test_mcp_tool_schema_does_not_expose_identity_arguments(engine) -> None:
    tenant_id = f"mcp-schema-{uuid4()}"
    server = build_test_server(engine, tenant_id)

    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == ["resolve_context"]
    properties = tools[0].input_schema["properties"]
    assert set(properties) == {
        "domains",
        "keys",
        "task",
        "audience",
        "environment",
    }
    assert {
        "tenant_id",
        "user_id",
        "agent_id",
        "client_id",
        "roles",
        "groups",
        "scopes",
    }.isdisjoint(properties)


def test_mcp_resolve_context_returns_same_runtime_contract_and_audits(engine) -> None:
    tenant_id = f"mcp-resolve-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.mcp",
                checksum_char="a",
                value="shared-runtime",
            ),
        )
        session.commit()

    server = build_test_server(engine, tenant_id)

    first = asyncio.run(
        server.call_tool(
            "resolve_context",
            {"domains": ["engineering"]},
        )
    )
    second = asyncio.run(
        server.call_tool(
            "resolve_context",
            {"domains": ["engineering"]},
        )
    )

    assert first.structured_content is not None
    assert second.structured_content is not None
    assert first.structured_content["tenant_id"] == tenant_id
    assert first.structured_content["context"][0]["key"] == "engineering.mcp"
    assert first.structured_content["context"][0]["value"] == {
        "value": "shared-runtime"
    }
    assert first.structured_content["resolution_id"] != second.structured_content[
        "resolution_id"
    ]


def test_mcp_extra_identity_argument_cannot_override_authenticated_principal(engine) -> None:
    tenant_id = f"mcp-injection-{uuid4()}"
    server = build_test_server(engine, tenant_id)

    result = asyncio.run(
        server.call_tool(
            "resolve_context",
            {
                "domains": ["engineering"],
                "tenant_id": "attacker-tenant",
                "user_id": "attacker-user",
            },
        )
    )

    assert result.structured_content is not None
    assert result.structured_content["tenant_id"] == tenant_id


def test_mcp_governance_conflict_returns_safe_tool_error(engine) -> None:
    tenant_id = f"mcp-conflict-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.conflict",
                checksum_char="b",
                value="left",
            ),
        )
        create_context_item(
            session,
            item(
                tenant_id=tenant_id,
                key="engineering.conflict",
                checksum_char="c",
                value="right",
            ),
        )
        session.commit()

    server = build_test_server(engine, tenant_id)

    with pytest.raises(ToolError, match="context governance conflict; resolution_id="):
        asyncio.run(
            server.call_tool(
                "resolve_context",
                {"domains": ["engineering"]},
            )
        )


def test_in_process_mcp_principal_without_resolve_permission_is_rejected(engine) -> None:
    tenant_id = f"mcp-permission-{uuid4()}"
    unauthorized = Principal(
        tenant_id=tenant_id,
        subject="mcp-user",
        kind=PrincipalKind.USER,
        client_id="mcp-client",
        roles=frozenset({"developer"}),
        groups=frozenset({"platform"}),
        scopes=frozenset({"context.read"}),
    )
    server = build_mcp_server(
        engine=engine,
        cache=InMemoryResolutionCache(ttl_seconds=60, max_entries=16),
        rules_provider=tuple,
        principal_provider=lambda: unauthorized,
    )

    with pytest.raises(ToolError, match="insufficient permission"):
        asyncio.run(
            server.call_tool(
                "resolve_context",
                {"domains": ["engineering"]},
            )
        )
