import asyncio
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from sqlalchemy.orm import Session

from contextplane.auth import Principal, PrincipalKind
from contextplane.cache import InMemoryResolutionCache
from contextplane.context_registry.seed import load_seed_file
from contextplane.database import build_engine
from contextplane.mcp import build_mcp_server
from contextplane.settings import Settings

pytestmark = pytest.mark.integration

TENANT = "copilot-demo-org"
FIXTURE = Path("examples/copilot-studio/context.yaml")


def principal(subject: str) -> Principal:
    return Principal(
        tenant_id=TENANT,
        subject=subject,
        kind=PrincipalKind.USER,
        client_id="copilot-studio-demo-client",
        roles=frozenset({"proposal-author"}),
        groups=frozenset({"demo-users"}),
        scopes=frozenset({"context.resolve"}),
    )


@pytest.fixture
def engine():
    db_engine = build_engine(Settings())
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def build_demo_server(engine, subject: str, cache: InMemoryResolutionCache):
    return build_mcp_server(
        engine=engine,
        cache=cache,
        rules_provider=tuple,
        principal_provider=lambda: principal(subject),
    )


def call(server, *, audience: str):
    result = asyncio.run(
        server.call_tool(
            "get_brand_presentation_context",
            {
                "audience": audience,
                "task": "draft external executive proposal",
            },
        )
    )
    assert result.structured_content is not None
    return result.structured_content


def test_same_agent_returns_shared_and_user_specific_context(engine) -> None:
    with Session(engine) as session:
        load_seed_file(session, FIXTURE)
        session.commit()

    cache = InMemoryResolutionCache(ttl_seconds=60, max_entries=32)
    marketing = build_demo_server(engine, "marketing-user", cache)
    engineering = build_demo_server(engine, "engineering-user", cache)

    marketing_result = call(marketing, audience="executive")
    engineering_result = call(engineering, audience="executive")

    marketing_keys = {item["key"] for item in marketing_result["context"]}
    engineering_keys = {item["key"] for item in engineering_result["context"]}

    assert marketing_keys == {
        "presentation.executive.structure",
        "presentation.user.marketing",
    }
    assert engineering_keys == {
        "presentation.executive.structure",
        "presentation.user.engineering",
    }
    assert "presentation.user.engineering" not in marketing_keys
    assert "presentation.user.marketing" not in engineering_keys
    assert marketing_result["tenant_id"] == TENANT
    assert engineering_result["tenant_id"] == TENANT
    assert marketing_result["resolution_id"] != engineering_result["resolution_id"]


def test_external_brand_context_is_shared_without_user_identity_argument(engine) -> None:
    with Session(engine) as session:
        load_seed_file(session, FIXTURE)
        session.commit()

    cache = InMemoryResolutionCache(ttl_seconds=60, max_entries=32)
    marketing = build_demo_server(engine, "marketing-user", cache)
    engineering = build_demo_server(engine, "engineering-user", cache)

    marketing_result = call(marketing, audience="external")
    engineering_result = call(engineering, audience="external")

    assert {item["key"] for item in marketing_result["context"]} == {
        "brand.external.voice"
    }
    assert {item["key"] for item in engineering_result["context"]} == {
        "brand.external.voice"
    }


def test_authoritative_rule_change_updates_subsequent_agent_context(
    engine,
    tmp_path: Path,
) -> None:
    with Session(engine) as session:
        load_seed_file(session, FIXTURE)
        session.commit()

    cache = InMemoryResolutionCache(ttl_seconds=600, max_entries=32)
    server = build_demo_server(engine, "marketing-user", cache)

    before = call(server, audience="executive")
    before_structure = next(
        item
        for item in before["context"]
        if item["key"] == "presentation.executive.structure"
    )
    assert before_structure["value"]["max_bullets_per_slide"] == 5

    payload = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))
    changed = deepcopy(payload)
    executive = next(
        item
        for item in changed["items"]
        if item["key"] == "presentation.executive.structure"
    )
    executive["value"]["max_bullets_per_slide"] = 4

    changed_path = tmp_path / "context.yaml"
    changed_path.write_text(yaml.safe_dump(changed, sort_keys=False), encoding="utf-8")

    with Session(engine) as session:
        results = load_seed_file(session, changed_path)
        session.commit()

    updated = next(
        result
        for result in results
        if result.key == "presentation.executive.structure"
    )
    assert updated.status == "superseded"

    after = call(server, audience="executive")
    after_structure = next(
        item
        for item in after["context"]
        if item["key"] == "presentation.executive.structure"
    )
    assert after_structure["value"]["max_bullets_per_slide"] == 4
    assert after["resolution_id"] != before["resolution_id"]


def test_copilot_helper_schema_exposes_no_identity_selector(engine) -> None:
    cache = InMemoryResolutionCache(ttl_seconds=60, max_entries=32)
    server = build_demo_server(engine, "marketing-user", cache)

    tools = asyncio.run(server.list_tools())
    helper = next(
        tool
        for tool in tools
        if tool.name == "get_brand_presentation_context"
    )

    properties = helper.input_schema["properties"]
    assert {
        "tenant_id",
        "user_id",
        "agent_id",
        "client_id",
        "roles",
        "groups",
        "scopes",
    }.isdisjoint(properties)



def test_copilot_demo_does_not_cross_tenant_boundary(engine) -> None:
    with Session(engine) as session:
        load_seed_file(session, FIXTURE)
        session.commit()

    cache = InMemoryResolutionCache(ttl_seconds=60, max_entries=32)
    outsider = build_mcp_server(
        engine=engine,
        cache=cache,
        rules_provider=tuple,
        principal_provider=lambda: Principal(
            tenant_id="other-tenant",
            subject="marketing-user",
            kind=PrincipalKind.USER,
            client_id="copilot-studio-demo-client",
            roles=frozenset({"proposal-author"}),
            groups=frozenset({"demo-users"}),
            scopes=frozenset({"context.resolve"}),
        ),
    )

    result = call(outsider, audience="executive")

    assert result["tenant_id"] == "other-tenant"
    assert result["context"] == []
