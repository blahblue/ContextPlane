"""Reproducible MVP evaluation harness for ContextPlane."""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from contextplane.api.dependencies import (
    authenticate_principal,
    get_database_session,
    get_policy_rules,
    get_resolution_cache,
)
from contextplane.app import app
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
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.repository import (
    create_context_item,
    supersede_context_item,
)
from contextplane.database import build_engine
from contextplane.mcp import build_mcp_server
from contextplane.policy import PolicyEffect, PolicyRule
from contextplane.runtime import ResolveContextRequest, resolve_context_runtime
from contextplane.settings import Settings

BENCHMARK_ITERATIONS = 40
NOW = datetime.now(UTC)


class EvaluationReport(BaseModel):
    """Machine-readable MVP evaluation result."""

    model_config = ConfigDict(extra="forbid")

    benchmark_iterations: int
    warm_runtime_p50_ms: float
    warm_runtime_p95_ms: float
    returned_context_items: int
    unexpected_context_items: int
    over_retrieval_rate: float
    golden_scenarios_passed: int
    golden_scenarios_total: int
    rule_accuracy: float
    policy_violations: int
    stale_context_pass: bool
    rest_mcp_consistent: bool
    passed: bool


def _principal(tenant_id: str) -> Principal:
    return Principal(
        tenant_id=tenant_id,
        subject="evaluation-user",
        kind=PrincipalKind.USER,
        client_id="evaluation-client",
        roles=frozenset({"developer"}),
        groups=frozenset({"engineering"}),
        scopes=frozenset({"context.resolve"}),
    )


def _item(
    *,
    tenant_id: str,
    key: str,
    checksum_char: str,
    value: str,
    repository: str | None = None,
    domain: ContextDomain = ContextDomain.ENGINEERING,
) -> ContextItemCreate:
    return ContextItemCreate(
        key=key,
        value={"value": value},
        domain=domain,
        scope=ContextScope(
            tenant_id=tenant_id,
            repository=repository,
            environment="production",
        ),
        owner="evaluation-suite",
        source=ContextSource(
            type=SourceType.MANUAL,
            identifier=f"evaluation-{key}-{checksum_char}",
        ),
        authority_level=AuthorityLevel.STANDARD,
        effective_from=NOW - timedelta(days=1),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum=checksum_char * 64,
    )


def _seed(engine: Engine, tenant_id: str) -> None:
    with Session(engine) as session:
        for context_item in (
            _item(
                tenant_id=tenant_id,
                key="engineering.shared.testing",
                checksum_char="a",
                value="pytest",
            ),
            _item(
                tenant_id=tenant_id,
                key="engineering.checkout.framework",
                checksum_char="b",
                value="FastAPI",
                repository="checkout-api",
            ),
            _item(
                tenant_id=tenant_id,
                key="engineering.catalog.framework",
                checksum_char="c",
                value="Django",
                repository="catalog-api",
            ),
            _item(
                tenant_id=tenant_id,
                key="security.secret-handling",
                checksum_char="d",
                value="never-log-secrets",
                repository="checkout-api",
                domain=ContextDomain.SECURITY,
            ),
        ):
            create_context_item(session, context_item)
        session.commit()


def _semantic_context(payload: dict[str, object]) -> list[tuple[str, object]]:
    raw_context = payload.get("context")
    if not isinstance(raw_context, list):
        raise ValueError("response context must be a list")
    semantic: list[tuple[str, object]] = []
    for raw in raw_context:
        if not isinstance(raw, dict):
            raise ValueError("response context item must be an object")
        semantic.append((str(raw["key"]), raw["value"]))
    return sorted(semantic, key=lambda item: item[0])


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def run_evaluation(engine: Engine) -> EvaluationReport:
    """Run the reproducible evaluation against one isolated tenant."""
    tenant_id = f"evaluation-{uuid4()}"
    principal = _principal(tenant_id)
    cache = InMemoryResolutionCache(ttl_seconds=600, max_entries=128)
    _seed(engine, tenant_id)

    checkout_request = ResolveContextRequest(
        domains=frozenset({ContextDomain.ENGINEERING}),
        repository="checkout-api",
        environment="production",
    )

    golden_expected = {
        "checkout": {
            "engineering.shared.testing",
            "engineering.checkout.framework",
        },
        "catalog": {
            "engineering.shared.testing",
            "engineering.catalog.framework",
        },
        "security": {"security.secret-handling"},
        "unknown": {"engineering.shared.testing"},
    }
    golden_actual: dict[str, set[str]] = {}

    with Session(engine) as session:
        for name, request in (
            ("checkout", checkout_request),
            (
                "catalog",
                ResolveContextRequest(
                    domains=frozenset({ContextDomain.ENGINEERING}),
                    repository="catalog-api",
                    environment="production",
                ),
            ),
            (
                "security",
                ResolveContextRequest(
                    domains=frozenset({ContextDomain.SECURITY}),
                    repository="checkout-api",
                    environment="production",
                ),
            ),
            (
                "unknown",
                ResolveContextRequest(
                    domains=frozenset({ContextDomain.ENGINEERING}),
                    repository="unknown-api",
                    environment="production",
                ),
            ),
        ):
            response = resolve_context_runtime(
                request=request,
                principal=principal,
                session=session,
                rules=(),
                cache=cache,
                as_of=NOW,
            )
            golden_actual[name] = {item.key for item in response.context}

    passed_scenarios = sum(
        golden_actual[name] == expected
        for name, expected in golden_expected.items()
    )

    checkout_keys = golden_actual["checkout"]
    unexpected = checkout_keys - golden_expected["checkout"]
    over_retrieval_rate = (
        len(unexpected) / len(checkout_keys)
        if checkout_keys
        else 0.0
    )

    deny_security = PolicyRule(
        rule_id="evaluation-deny-security",
        tenant_id=tenant_id,
        authority_level=AuthorityLevel.MANDATORY_CONTROL,
        effect=PolicyEffect.DENY,
        target_domains=frozenset({ContextDomain.SECURITY}),
        reason="evaluation policy denial",
    )
    with Session(engine) as session:
        denied = resolve_context_runtime(
            request=ResolveContextRequest(
                domains=frozenset({ContextDomain.SECURITY}),
                repository="checkout-api",
                environment="production",
            ),
            principal=principal,
            session=session,
            rules=(deny_security,),
            cache=cache,
            as_of=NOW,
        )
    policy_violations = len(denied.context)

    timings: list[float] = []
    with Session(engine) as session:
        resolve_context_runtime(
            request=checkout_request,
            principal=principal,
            session=session,
            rules=(),
            cache=cache,
            as_of=NOW,
        )
        for _ in range(BENCHMARK_ITERATIONS):
            started = time.perf_counter()
            resolve_context_runtime(
                request=checkout_request,
                principal=principal,
                session=session,
                rules=(),
                cache=cache,
                as_of=NOW,
            )
            timings.append((time.perf_counter() - started) * 1000)

    stale_key = "engineering.checkout.framework"
    with Session(engine) as session:
        first = session.scalar(
            select(ContextItemRecord).where(
                ContextItemRecord.tenant_id == tenant_id,
                ContextItemRecord.key == stale_key,
                ContextItemRecord.version == 1,
            )
        )
        if first is None:
            raise RuntimeError("evaluation fixture record was not found")
        first_id = first.id

    with Session(engine) as session:
        before = resolve_context_runtime(
            request=checkout_request,
            principal=principal,
            session=session,
            rules=(),
            cache=cache,
            as_of=NOW,
        )
    before_framework = next(item for item in before.context if item.key == stale_key)

    with Session(engine) as session:
        supersede_context_item(
            session,
            tenant_id=tenant_id,
            previous_id=first_id,
            replacement=_item(
                tenant_id=tenant_id,
                key=stale_key,
                checksum_char="e",
                value="FastAPI-v2",
                repository="checkout-api",
            ),
        )
        session.commit()

    with Session(engine) as session:
        after = resolve_context_runtime(
            request=checkout_request,
            principal=principal,
            session=session,
            rules=(),
            cache=cache,
            as_of=NOW,
        )
    after_framework = next(item for item in after.context if item.key == stale_key)
    stale_context_pass = (
        before_framework.version == 1
        and after_framework.version == 2
        and after_framework.value == {"value": "FastAPI-v2"}
    )

    def session_override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[authenticate_principal] = lambda: principal
    app.dependency_overrides[get_database_session] = session_override
    app.dependency_overrides[get_policy_rules] = tuple
    app.dependency_overrides[get_resolution_cache] = lambda: cache

    try:
        rest_client = TestClient(app)
        rest_response = rest_client.post(
            "/v1/context/resolve",
            headers={"Authorization": "Bearer evaluation"},
            json={
                "domains": ["engineering"],
                "repository": "checkout-api",
                "environment": "production",
            },
        )
        rest_response.raise_for_status()
        rest_payload = rest_response.json()
    finally:
        app.dependency_overrides.clear()

    mcp_server = build_mcp_server(
        engine=engine,
        cache=cache,
        rules_provider=tuple,
        principal_provider=lambda: principal,
    )
    mcp_result = asyncio.run(
        mcp_server.call_tool(
            "get_engineering_context",
            {
                "repository": "checkout-api",
                "environment": "production",
            },
        )
    )
    raw_mcp_content = getattr(mcp_result, "structured_content", None)
    if not isinstance(raw_mcp_content, dict):
        raise RuntimeError("MCP evaluation returned no structured content")
    mcp_payload = cast(dict[str, object], raw_mcp_content)

    rest_mcp_consistent = (
        _semantic_context(rest_payload)
        == _semantic_context(mcp_payload)
        and rest_payload["policy"]["decision"]
        == cast(dict[str, object], mcp_payload["policy"])["decision"]
    )

    p50 = statistics.median(timings)
    p95 = _percentile(timings, 0.95)
    rule_accuracy = passed_scenarios / len(golden_expected)

    passed = (
        rule_accuracy == 1.0
        and not unexpected
        and policy_violations == 0
        and stale_context_pass
        and rest_mcp_consistent
        and p95 < 250.0
    )

    return EvaluationReport(
        benchmark_iterations=BENCHMARK_ITERATIONS,
        warm_runtime_p50_ms=round(p50, 3),
        warm_runtime_p95_ms=round(p95, 3),
        returned_context_items=len(checkout_keys),
        unexpected_context_items=len(unexpected),
        over_retrieval_rate=round(over_retrieval_rate, 6),
        golden_scenarios_passed=passed_scenarios,
        golden_scenarios_total=len(golden_expected),
        rule_accuracy=round(rule_accuracy, 6),
        policy_violations=policy_violations,
        stale_context_pass=stale_context_pass,
        rest_mcp_consistent=rest_mcp_consistent,
        passed=passed,
    )


def main() -> None:
    """Run evaluation and print a machine-readable JSON report."""
    engine = build_engine(Settings())
    try:
        report = run_evaluation(engine)
    finally:
        engine.dispose()

    print(json.dumps(report.model_dump(mode="json"), sort_keys=True))
    if not report.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
