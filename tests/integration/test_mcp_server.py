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


def test_mcp_tool_schemas_do_not_expose_identity_arguments(engine) -> None:
    tenant_id = f"mcp-schema-{uuid4()}"
    server = build_test_server(engine, tenant_id)

    tools = asyncio.run(server.list_tools())
    schemas = {tool.name: tool.input_schema["properties"] for tool in tools}

    assert set(schemas) == {
        "resolve_context",
        "get_engineering_context",
        "get_brand_presentation_context",
        "get_policy_context",
    }
    assert set(schemas["resolve_context"]) == {
        "domains",
        "keys",
        "task",
        "audience",
        "environment",
        "repository",
        "resource",
    }

    forbidden = {
        "tenant_id",
        "user_id",
        "agent_id",
        "client_id",
        "roles",
        "groups",
        "scopes",
    }
    for properties in schemas.values():
        assert forbidden.isdisjoint(properties)

    for helper_name in {
        "get_engineering_context",
        "get_brand_presentation_context",
        "get_policy_context",
    }:
        assert "domains" not in schemas[helper_name]


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



def create_domain_item(
    *,
    tenant_id: str,
    key: str,
    domain: ContextDomain,
    checksum_char: str,
    value: str,
    repository: str | None = None,
    audience: str | None = None,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"value": value},
        domain=domain,
        scope=ContextScope(
            tenant_id=tenant_id,
            repository=repository,
            audience=audience,
        ),
        owner="mcp-helper-test-owner",
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


def test_domain_helpers_pin_domains_and_use_shared_runtime(engine) -> None:
    tenant_id = f"mcp-helpers-{uuid4()}"

    with Session(engine) as session:
        for item_to_create in (
            create_domain_item(
                tenant_id=tenant_id,
                key="engineering.helper",
                domain=ContextDomain.ENGINEERING,
                checksum_char="d",
                value="engineering",
            ),
            create_domain_item(
                tenant_id=tenant_id,
                key="brand.helper",
                domain=ContextDomain.BRAND,
                checksum_char="e",
                value="brand",
            ),
            create_domain_item(
                tenant_id=tenant_id,
                key="presentation.helper",
                domain=ContextDomain.PRESENTATION,
                checksum_char="f",
                value="presentation",
            ),
            create_domain_item(
                tenant_id=tenant_id,
                key="security.helper",
                domain=ContextDomain.SECURITY,
                checksum_char="1",
                value="security",
            ),
        ):
            create_context_item(session, item_to_create)
        session.commit()

    server = build_test_server(engine, tenant_id)

    engineering = asyncio.run(
        server.call_tool("get_engineering_context", {})
    )
    brand_presentation = asyncio.run(
        server.call_tool("get_brand_presentation_context", {})
    )
    policy = asyncio.run(
        server.call_tool("get_policy_context", {})
    )

    assert engineering.structured_content is not None
    assert brand_presentation.structured_content is not None
    assert policy.structured_content is not None

    assert {
        item["domain"] for item in engineering.structured_content["context"]
    } == {"engineering"}
    assert {
        item["domain"] for item in brand_presentation.structured_content["context"]
    } == {"brand", "presentation"}
    assert {
        item["domain"] for item in policy.structured_content["context"]
    } == {"security"}

    resolution_ids = {
        engineering.structured_content["resolution_id"],
        brand_presentation.structured_content["resolution_id"],
        policy.structured_content["resolution_id"],
    }
    assert len(resolution_ids) == 3


def test_engineering_helper_respects_repository_scope(engine) -> None:
    tenant_id = f"mcp-repository-{uuid4()}"

    with Session(engine) as session:
        create_context_item(
            session,
            create_domain_item(
                tenant_id=tenant_id,
                key="engineering.repository",
                domain=ContextDomain.ENGINEERING,
                checksum_char="2",
                value="checkout-standard",
                repository="checkout-api",
            ),
        )
        session.commit()

    server = build_test_server(engine, tenant_id)

    matching = asyncio.run(
        server.call_tool(
            "get_engineering_context",
            {"repository": "checkout-api"},
        )
    )
    nonmatching = asyncio.run(
        server.call_tool(
            "get_engineering_context",
            {"repository": "catalog-api"},
        )
    )

    assert matching.structured_content is not None
    assert nonmatching.structured_content is not None
    assert [item["key"] for item in matching.structured_content["context"]] == [
        "engineering.repository"
    ]
    assert nonmatching.structured_content["context"] == []


def test_helper_tool_cannot_select_another_domain(engine) -> None:
    tenant_id = f"mcp-helper-injection-{uuid4()}"
    server = build_test_server(engine, tenant_id)

    result = asyncio.run(
        server.call_tool(
            "get_engineering_context",
            {
                "domains": ["security"],
                "tenant_id": "attacker-tenant",
            },
        )
    )

    assert result.structured_content is not None
    assert result.structured_content["tenant_id"] == tenant_id
    assert result.structured_content["policy"]["allowed_domains"] == ["engineering"]
