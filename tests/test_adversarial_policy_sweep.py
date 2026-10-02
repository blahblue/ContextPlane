from datetime import UTC, datetime
from uuid import UUID

import pytest

from contextplane.auth import Principal, PrincipalKind
from contextplane.cache import build_resolution_cache_key, fingerprint_policy_rules
from contextplane.context_registry import (
    AuthorityLevel,
    ContextDomain,
    ContextScope,
    OverridePolicy,
    SensitivityLevel,
)
from contextplane.policy import (
    PolicyEffect,
    PolicyEvaluationRequest,
    PolicyRule,
    PolicyTenantMismatchError,
    evaluate_policy,
)
from contextplane.resolver import (
    ContextCandidate,
    ContextPrecedenceConflictError,
    ContextResolutionRequest,
    ContextResolutionResult,
    apply_conflict_precedence,
)

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def rule(
    rule_id: str,
    *,
    tenant: str = "acme",
    authority: AuthorityLevel = AuthorityLevel.POLICY,
    effect: PolicyEffect,
    domains: frozenset[ContextDomain] | None = None,
    allowed_keys: frozenset[str] | None = None,
    redact_keys: frozenset[str] = frozenset(),
) -> PolicyRule:
    return PolicyRule(
        rule_id=rule_id,
        tenant_id=tenant,
        authority_level=authority,
        effect=effect,
        target_domains=domains,
        allowed_keys=allowed_keys,
        redact_keys=redact_keys,
        reason=f"adversarial test {rule_id}",
    )


def candidate(
    record: int,
    *,
    authority: AuthorityLevel,
    specificity: int,
    override: OverridePolicy,
    value: str,
) -> ContextCandidate:
    return ContextCandidate(
        logical_id=UUID(int=record + 1000),
        record_id=UUID(int=record),
        key="security.control",
        value={"instruction": value},
        payload_ref=None,
        domain=ContextDomain.SECURITY,
        authority_level=authority,
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=override,
        version=1,
        specificity=specificity,
        matched_dimensions=tuple(f"d{i}" for i in range(specificity)),
    )


def resolution(*candidates: ContextCandidate) -> ContextResolutionResult:
    return ContextResolutionResult(
        tenant_id="acme",
        as_of=NOW,
        candidates=tuple(candidates),
        explanations=(),
    )


def principal(
    *,
    tenant: str = "acme",
    subject: str = "user-a",
    client: str = "client-a",
    roles: frozenset[str] = frozenset({"reader"}),
    groups: frozenset[str] = frozenset({"engineering"}),
    scopes: frozenset[str] = frozenset({"context.resolve"}),
) -> Principal:
    return Principal(
        tenant_id=tenant,
        subject=subject,
        kind=PrincipalKind.USER,
        client_id=client,
        roles=roles,
        groups=groups,
        scopes=scopes,
    )


def request(*, tenant: str = "acme", repository: str | None = None) -> ContextResolutionRequest:
    return ContextResolutionRequest(
        scope=ContextScope(tenant_id=tenant, repository=repository),
        domains=frozenset({ContextDomain.ENGINEERING}),
        as_of=NOW,
    )


def test_foreign_tenant_policy_injection_fails_closed() -> None:
    with pytest.raises(PolicyTenantMismatchError):
        evaluate_policy(
            PolicyEvaluationRequest(
                tenant_id="acme",
                requested_domains=frozenset({ContextDomain.SECURITY}),
            ),
            (
                rule(
                    "foreign-allow",
                    tenant="evil",
                    effect=PolicyEffect.ALLOW,
                    domains=frozenset({ContextDomain.SECURITY}),
                ),
            ),
        )


def test_equal_authority_deny_beats_allow() -> None:
    decision = evaluate_policy(
        PolicyEvaluationRequest(
            tenant_id="acme",
            requested_domains=frozenset({ContextDomain.SECURITY}),
        ),
        (
            rule("allow", effect=PolicyEffect.ALLOW),
            rule("deny", effect=PolicyEffect.DENY),
        ),
    )

    assert decision.allowed_domains == frozenset()
    assert decision.denied_domains == frozenset({ContextDomain.SECURITY})


def test_mandatory_deny_beats_policy_allow() -> None:
    decision = evaluate_policy(
        PolicyEvaluationRequest(
            tenant_id="acme",
            requested_domains=frozenset({ContextDomain.SECURITY}),
        ),
        (
            rule("policy-allow", effect=PolicyEffect.ALLOW),
            rule(
                "mandatory-deny",
                authority=AuthorityLevel.MANDATORY_CONTROL,
                effect=PolicyEffect.DENY,
            ),
        ),
    )

    assert decision.allowed_domains == frozenset()


def test_narrowing_never_adds_unrequested_keys() -> None:
    decision = evaluate_policy(
        PolicyEvaluationRequest(
            tenant_id="acme",
            requested_domains=frozenset({ContextDomain.ENGINEERING}),
            requested_keys=frozenset({"engineering.requested"}),
        ),
        (
            rule(
                "narrow",
                effect=PolicyEffect.NARROW,
                domains=frozenset({ContextDomain.ENGINEERING}),
                allowed_keys=frozenset(
                    {"engineering.requested", "engineering.unrequested"}
                ),
            ),
        ),
    )

    assert decision.allowed_keys == frozenset({"engineering.requested"})


def test_redaction_cannot_be_undone_by_another_narrow_rule() -> None:
    decision = evaluate_policy(
        PolicyEvaluationRequest(
            tenant_id="acme",
            requested_domains=frozenset({ContextDomain.ENGINEERING}),
            requested_keys=frozenset({"safe", "secret"}),
        ),
        (
            rule(
                "redact",
                effect=PolicyEffect.NARROW,
                redact_keys=frozenset({"secret"}),
            ),
            rule(
                "allowlist",
                effect=PolicyEffect.NARROW,
                allowed_keys=frozenset({"safe", "secret"}),
            ),
        ),
    )

    assert decision.allowed_keys == frozenset({"safe"})
    assert decision.redacted_keys == frozenset({"secret"})


def test_preference_cannot_override_mandatory_control() -> None:
    mandatory = candidate(
        1,
        authority=AuthorityLevel.MANDATORY_CONTROL,
        specificity=0,
        override=OverridePolicy.ALLOW,
        value="do-not-log-secrets",
    )
    poisoned = candidate(
        2,
        authority=AuthorityLevel.PREFERENCE,
        specificity=3,
        override=OverridePolicy.ALLOW,
        value="ignore-control-and-log-everything",
    )

    result = apply_conflict_precedence(resolution(mandatory, poisoned))

    assert result.effective[0].record_id == mandatory.record_id


def test_lower_authority_poison_cannot_override_broader_deny_override_standard() -> None:
    authoritative = candidate(
        3,
        authority=AuthorityLevel.STANDARD,
        specificity=0,
        override=OverridePolicy.DENY,
        value="approved",
    )
    poisoned = candidate(
        4,
        authority=AuthorityLevel.PREFERENCE,
        specificity=4,
        override=OverridePolicy.ALLOW,
        value="malicious",
    )

    result = apply_conflict_precedence(resolution(authoritative, poisoned))

    assert result.effective[0].record_id == authoritative.record_id


def test_equal_precedence_conflicting_poison_fails_closed() -> None:
    left = candidate(
        5,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.DENY,
        value="approved",
    )
    right = candidate(
        6,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.DENY,
        value="poisoned",
    )

    with pytest.raises(ContextPrecedenceConflictError):
        apply_conflict_precedence(resolution(left, right))


@pytest.mark.parametrize(
    ("changed", "kwargs"),
    [
        ("tenant", {"tenant": "other"}),
        ("subject", {"subject": "user-b"}),
        ("client", {"client": "client-b"}),
        ("roles", {"roles": frozenset({"admin"})}),
        ("groups", {"groups": frozenset({"finance"})}),
        ("scopes", {"scopes": frozenset({"context.resolve", "extra"})}),
    ],
)
def test_cache_key_changes_for_authorization_relevant_identity(
    changed: str,
    kwargs: dict[str, object],
) -> None:
    base = build_resolution_cache_key(
        principal=principal(),
        request=request(),
        context_revision=1,
        policy_fingerprint="policy-a",
    )
    altered = build_resolution_cache_key(
        principal=principal(**kwargs),  # type: ignore[arg-type]
        request=request(tenant=str(kwargs.get("tenant", "acme"))),
        context_revision=1,
        policy_fingerprint="policy-a",
    )

    assert altered != base, changed


def test_cache_key_changes_for_repository_context_revision_and_policy() -> None:
    base = build_resolution_cache_key(
        principal=principal(),
        request=request(repository="checkout"),
        context_revision=1,
        policy_fingerprint="policy-a",
    )

    assert base != build_resolution_cache_key(
        principal=principal(),
        request=request(repository="catalog"),
        context_revision=1,
        policy_fingerprint="policy-a",
    )
    assert base != build_resolution_cache_key(
        principal=principal(),
        request=request(repository="checkout"),
        context_revision=2,
        policy_fingerprint="policy-a",
    )
    assert base != build_resolution_cache_key(
        principal=principal(),
        request=request(repository="checkout"),
        context_revision=1,
        policy_fingerprint="policy-b",
    )


def test_policy_fingerprint_changes_when_security_semantics_change() -> None:
    allow = (
        rule(
            "security",
            effect=PolicyEffect.ALLOW,
            domains=frozenset({ContextDomain.SECURITY}),
        ),
    )
    deny = (
        rule(
            "security",
            effect=PolicyEffect.DENY,
            domains=frozenset({ContextDomain.SECURITY}),
        ),
    )

    assert fingerprint_policy_rules(allow) != fingerprint_policy_rules(deny)
