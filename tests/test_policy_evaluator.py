import pytest
from pydantic import ValidationError

from contextplane.context_registry import AuthorityLevel, ContextDomain
from contextplane.policy import (
    PolicyDecisionKind,
    PolicyEffect,
    PolicyEvaluationRequest,
    PolicyRule,
    PolicyTenantMismatchError,
    evaluate_policy,
)


def rule(
    *,
    rule_id: str,
    effect: PolicyEffect,
    authority: AuthorityLevel = AuthorityLevel.POLICY,
    domains: frozenset[ContextDomain] | None = None,
    allowed_keys: frozenset[str] | None = None,
    redact_keys: frozenset[str] = frozenset(),
    tenant_id: str = "acme",
) -> PolicyRule:
    return PolicyRule(
        rule_id=rule_id,
        tenant_id=tenant_id,
        authority_level=authority,
        effect=effect,
        target_domains=domains,
        allowed_keys=allowed_keys,
        redact_keys=redact_keys,
        reason=f"test rule {rule_id}",
    )


def request(
    *domains: ContextDomain,
    keys: frozenset[str] | None = None,
) -> PolicyEvaluationRequest:
    return PolicyEvaluationRequest(
        tenant_id="acme",
        requested_domains=frozenset(domains),
        requested_keys=keys,
    )


def test_default_is_allow_without_policy_rules() -> None:
    result = evaluate_policy(
        request(ContextDomain.ENGINEERING, ContextDomain.SECURITY),
        [],
    )

    assert result.decision is PolicyDecisionKind.ALLOW
    assert result.allowed_domains == {
        ContextDomain.ENGINEERING,
        ContextDomain.SECURITY,
    }
    assert result.denied_domains == frozenset()


def test_policy_deny_removes_targeted_domain_only() -> None:
    result = evaluate_policy(
        request(ContextDomain.ENGINEERING, ContextDomain.SECURITY),
        [
            rule(
                rule_id="deny-engineering",
                effect=PolicyEffect.DENY,
                domains=frozenset({ContextDomain.ENGINEERING}),
            )
        ],
    )

    assert result.decision is PolicyDecisionKind.NARROW
    assert result.allowed_domains == {ContextDomain.SECURITY}
    assert result.denied_domains == {ContextDomain.ENGINEERING}


def test_mandatory_allow_overrides_lower_authority_deny() -> None:
    result = evaluate_policy(
        request(ContextDomain.ENGINEERING),
        [
            rule(rule_id="policy-deny", effect=PolicyEffect.DENY),
            rule(
                rule_id="mandatory-allow",
                effect=PolicyEffect.ALLOW,
                authority=AuthorityLevel.MANDATORY_CONTROL,
            ),
        ],
    )

    assert result.decision is PolicyDecisionKind.ALLOW
    assert result.allowed_domains == {ContextDomain.ENGINEERING}
    assert result.domain_decisions[0].decisive_rule_ids == ("mandatory-allow",)


def test_mandatory_deny_overrides_lower_authority_allow() -> None:
    result = evaluate_policy(
        request(ContextDomain.ENGINEERING),
        [
            rule(rule_id="policy-allow", effect=PolicyEffect.ALLOW),
            rule(
                rule_id="mandatory-deny",
                effect=PolicyEffect.DENY,
                authority=AuthorityLevel.MANDATORY_CONTROL,
            ),
        ],
    )

    assert result.decision is PolicyDecisionKind.DENY
    assert result.denied_domains == {ContextDomain.ENGINEERING}


def test_deny_wins_equal_authority_admission_tie() -> None:
    result = evaluate_policy(
        request(ContextDomain.ENGINEERING),
        [
            rule(rule_id="allow", effect=PolicyEffect.ALLOW),
            rule(rule_id="deny", effect=PolicyEffect.DENY),
        ],
    )

    assert result.decision is PolicyDecisionKind.DENY
    assert result.domain_decisions[0].decisive_rule_ids == ("allow", "deny")


def test_narrow_allowlists_intersect_and_redactions_union() -> None:
    result = evaluate_policy(
        request(
            ContextDomain.ENGINEERING,
            keys=frozenset({"a", "b", "c", "secret"}),
        ),
        [
            rule(
                rule_id="narrow-one",
                effect=PolicyEffect.NARROW,
                allowed_keys=frozenset({"a", "b", "secret"}),
                redact_keys=frozenset({"secret"}),
            ),
            rule(
                rule_id="narrow-two",
                effect=PolicyEffect.NARROW,
                allowed_keys=frozenset({"b", "c", "secret"}),
                redact_keys=frozenset({"c"}),
            ),
        ],
    )

    assert result.decision is PolicyDecisionKind.NARROW
    assert result.allowed_keys == {"b"}
    assert result.redacted_keys == {"secret", "c"}
    assert result.narrowing_rule_ids == ("narrow-one", "narrow-two")


def test_narrowing_is_monotonic_even_with_mandatory_allow() -> None:
    result = evaluate_policy(
        request(
            ContextDomain.SECURITY,
            keys=frozenset({"public", "restricted"}),
        ),
        [
            rule(
                rule_id="redact-restricted",
                effect=PolicyEffect.NARROW,
                redact_keys=frozenset({"restricted"}),
            ),
            rule(
                rule_id="mandatory-allow",
                effect=PolicyEffect.ALLOW,
                authority=AuthorityLevel.MANDATORY_CONTROL,
            ),
        ],
    )

    assert result.allowed_domains == {ContextDomain.SECURITY}
    assert result.allowed_keys == {"public"}
    assert result.decision is PolicyDecisionKind.NARROW


def test_narrow_rule_for_denied_domain_does_not_affect_remaining_domain() -> None:
    result = evaluate_policy(
        request(
            ContextDomain.ENGINEERING,
            ContextDomain.SECURITY,
            keys=frozenset({"a", "b"}),
        ),
        [
            rule(
                rule_id="deny-engineering",
                effect=PolicyEffect.DENY,
                domains=frozenset({ContextDomain.ENGINEERING}),
            ),
            rule(
                rule_id="engineering-redaction",
                effect=PolicyEffect.NARROW,
                domains=frozenset({ContextDomain.ENGINEERING}),
                redact_keys=frozenset({"a"}),
            ),
        ],
    )

    assert result.allowed_domains == {ContextDomain.SECURITY}
    assert result.allowed_keys == {"a", "b"}
    assert result.narrowing_rule_ids == ()


def test_policy_rules_cannot_broaden_requested_domains() -> None:
    result = evaluate_policy(
        request(ContextDomain.BRAND),
        [
            rule(
                rule_id="allow-all",
                effect=PolicyEffect.ALLOW,
                authority=AuthorityLevel.MANDATORY_CONTROL,
            )
        ],
    )

    assert result.allowed_domains == {ContextDomain.BRAND}


def test_cross_tenant_rule_fails_closed() -> None:
    with pytest.raises(PolicyTenantMismatchError, match="different tenant"):
        evaluate_policy(
            request(ContextDomain.ENGINEERING),
            [
                rule(
                    rule_id="foreign",
                    effect=PolicyEffect.DENY,
                    tenant_id="other",
                )
            ],
        )


def test_executable_policy_rejects_non_policy_authority() -> None:
    with pytest.raises(ValidationError, match="requires policy"):
        rule(
            rule_id="preference-policy",
            effect=PolicyEffect.DENY,
            authority=AuthorityLevel.PREFERENCE,
        )


def test_narrow_rule_requires_actual_restriction() -> None:
    with pytest.raises(ValidationError, match="requires allowed_keys"):
        rule(rule_id="empty-narrow", effect=PolicyEffect.NARROW)


def test_allow_rule_cannot_hide_narrowing_fields() -> None:
    with pytest.raises(ValidationError, match="cannot carry key narrowing"):
        rule(
            rule_id="invalid-allow",
            effect=PolicyEffect.ALLOW,
            redact_keys=frozenset({"secret"}),
        )


def test_explicit_empty_target_domains_are_rejected() -> None:
    with pytest.raises(ValidationError, match="cannot be explicitly empty"):
        rule(
            rule_id="empty-target",
            effect=PolicyEffect.DENY,
            domains=frozenset(),
        )
