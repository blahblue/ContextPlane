"""Fail-closed policy evaluation for requested context surfaces."""

from collections.abc import Iterable

from contextplane.context_registry.domain import AuthorityLevel, ContextDomain
from contextplane.policy.domain import (
    PolicyDecision,
    PolicyDecisionKind,
    PolicyDomainDecision,
    PolicyEffect,
    PolicyEvaluationRequest,
    PolicyRule,
)

_AUTHORITY_RANK = {
    AuthorityLevel.POLICY: 1,
    AuthorityLevel.MANDATORY_CONTROL: 2,
}


class PolicyTenantMismatchError(ValueError):
    """Raised when policy rules from another tenant enter an evaluation."""


def _targets_domain(rule: PolicyRule, domain: ContextDomain) -> bool:
    """Return whether a rule applies to one requested domain."""
    return rule.target_domains is None or domain in rule.target_domains


def _admission_decision(
    domain: ContextDomain,
    rules: list[PolicyRule],
) -> PolicyDomainDecision:
    """Resolve allow/deny rules for one domain by authority with deny-safe ties."""
    admission = [
        rule
        for rule in rules
        if rule.effect in {PolicyEffect.ALLOW, PolicyEffect.DENY}
        and _targets_domain(rule, domain)
    ]
    if not admission:
        return PolicyDomainDecision(
            domain=domain,
            allowed=True,
            decisive_rule_ids=(),
            reason="default allow; no admission policy targeted this domain",
        )

    highest_rank = max(_AUTHORITY_RANK[rule.authority_level] for rule in admission)
    decisive = [
        rule
        for rule in admission
        if _AUTHORITY_RANK[rule.authority_level] == highest_rank
    ]
    decisive_ids = tuple(sorted(rule.rule_id for rule in decisive))

    if any(rule.effect is PolicyEffect.DENY for rule in decisive):
        return PolicyDomainDecision(
            domain=domain,
            allowed=False,
            decisive_rule_ids=decisive_ids,
            reason="deny wins among the highest-authority admission policies",
        )

    return PolicyDomainDecision(
        domain=domain,
        allowed=True,
        decisive_rule_ids=decisive_ids,
        reason="highest-authority admission policies allow this domain",
    )


def evaluate_policy(
    request: PolicyEvaluationRequest,
    rules: Iterable[PolicyRule],
) -> PolicyDecision:
    """Evaluate domain admission and monotonic key narrowing for one tenant."""
    policy_rules = list(rules)

    if any(rule.tenant_id != request.tenant_id for rule in policy_rules):
        raise PolicyTenantMismatchError(
            "policy evaluation received a rule from a different tenant"
        )

    domain_decisions = tuple(
        _admission_decision(domain, policy_rules)
        for domain in sorted(request.requested_domains, key=lambda item: item.value)
    )
    allowed_domains = frozenset(
        decision.domain for decision in domain_decisions if decision.allowed
    )
    denied_domains = request.requested_domains - allowed_domains

    narrowing = [
        rule
        for rule in policy_rules
        if allowed_domains
        and rule.effect is PolicyEffect.NARROW
        and (
            rule.target_domains is None
            or bool(rule.target_domains.intersection(allowed_domains))
        )
    ]

    key_allowlist: frozenset[str] | None = None
    redacted_keys: set[str] = set()

    for rule in narrowing:
        if rule.allowed_keys is not None:
            candidate_allowlist = frozenset(rule.allowed_keys)
            key_allowlist = (
                candidate_allowlist
                if key_allowlist is None
                else key_allowlist.intersection(candidate_allowlist)
            )
        redacted_keys.update(rule.redact_keys)

    if request.requested_keys is None:
        allowed_keys = (
            None
            if key_allowlist is None
            else key_allowlist.difference(redacted_keys)
        )
    else:
        allowed_keys = frozenset(request.requested_keys)
        if key_allowlist is not None:
            allowed_keys = allowed_keys.intersection(key_allowlist)
        allowed_keys = allowed_keys.difference(redacted_keys)

    if request.requested_domains and not allowed_domains:
        decision = PolicyDecisionKind.DENY
        if request.requested_keys is not None:
            allowed_keys = frozenset()
    elif denied_domains or narrowing:
        decision = PolicyDecisionKind.NARROW
    else:
        decision = PolicyDecisionKind.ALLOW

    return PolicyDecision(
        tenant_id=request.tenant_id,
        decision=decision,
        allowed_domains=allowed_domains,
        denied_domains=denied_domains,
        allowed_keys=allowed_keys,
        redacted_keys=frozenset(redacted_keys),
        domain_decisions=domain_decisions,
        narrowing_rule_ids=tuple(sorted(rule.rule_id for rule in narrowing)),
    )
