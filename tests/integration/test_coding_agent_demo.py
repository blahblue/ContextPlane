import asyncio
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from contextplane.auth import Principal, PrincipalKind
from contextplane.cache import InMemoryResolutionCache
from contextplane.context_registry.seed import load_seed_file
from contextplane.database import build_engine
from contextplane.mcp import build_mcp_server
from contextplane.settings import Settings

pytestmark = pytest.mark.integration

TENANT = "coding-demo-org"
FIXTURE = Path("examples/coding-agent/context.yaml")


def demo_principal() -> Principal:
    return Principal(
        tenant_id=TENANT,
        subject="coding-demo-user",
        kind=PrincipalKind.USER,
        client_id="cursor-demo-client",
        roles=frozenset({"developer"}),
        groups=frozenset({"engineering"}),
        scopes=frozenset({"context.resolve"}),
    )


@pytest.fixture
def engine():
    db_engine = build_engine(Settings())
    try:
        yield db_engine
    finally:
        db_engine.dispose()


def build_demo_server(engine):
    return build_mcp_server(
        engine=engine,
        cache=InMemoryResolutionCache(ttl_seconds=60, max_entries=32),
        rules_provider=tuple,
        principal_provider=demo_principal,
    )


def call(server, tool: str, arguments: dict[str, object]):
    return asyncio.run(server.call_tool(tool, arguments)).structured_content


def test_coding_agent_demo_returns_repository_specific_context(engine) -> None:
    with Session(engine) as session:
        load_seed_file(session, FIXTURE)
        session.commit()

    server = build_demo_server(engine)

    checkout = call(
        server,
        "get_engineering_context",
        {
            "repository": "checkout-api",
            "environment": "production",
            "task": "implement checkout session status endpoint",
        },
    )
    catalog = call(
        server,
        "get_engineering_context",
        {
            "repository": "catalog-api",
            "environment": "production",
            "task": "implement catalog item endpoint",
        },
    )
    checkout_policy = call(
        server,
        "get_policy_context",
        {
            "repository": "checkout-api",
            "environment": "production",
            "task": "implement checkout session status endpoint",
        },
    )

    assert checkout is not None
    assert catalog is not None
    assert checkout_policy is not None

    assert {item["key"] for item in checkout["context"]} == {
        "engineering.testing.required",
        "engineering.checkout.service_conventions",
    }
    assert {item["key"] for item in catalog["context"]} == {
        "engineering.testing.required",
        "engineering.catalog.service_conventions",
    }
    assert {item["key"] for item in checkout_policy["context"]} == {
        "security.checkout.secret_handling"
    }

    assert "engineering.catalog.service_conventions" not in {
        item["key"] for item in checkout["context"]
    }
    assert "engineering.checkout.service_conventions" not in {
        item["key"] for item in catalog["context"]
    }

    assert len(
        {
            checkout["resolution_id"],
            catalog["resolution_id"],
            checkout_policy["resolution_id"],
        }
    ) == 3
