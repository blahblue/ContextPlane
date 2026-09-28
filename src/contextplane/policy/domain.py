"""Validated models for ContextPlane policy evaluation."""

from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from contextplane.context_registry.domain import AuthorityLevel, ContextDomain

NonEmptyPolicyString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=512),
]


class PolicyEffect(StrEnum):
    """Supported admission and narrowing effects."""

    ALLOW = "allow"
    DENY = "deny"
    NARROW = "narrow"


class PolicyDecisionKind(StrEnum):
    """Overall result of evaluating requested context access."""

    ALLOW = "allow"
    DENY = "deny"
    NARROW = "narrow"


class PolicyRule(BaseModel):
    """One explicit policy rule evaluated by the ContextPlane gateway."""

    model_config = ConfigDict(extra="forbid")

    rule_id: NonEmptyPolicyString
    tenant_id: NonEmptyPolicyString
    authority_level: AuthorityLevel
    effect: PolicyEffect
    target_domains: frozenset[ContextDomain] | None = None
    allowed_keys: frozenset[NonEmptyPolicyString] | None = None
    redact_keys: frozenset[NonEmptyPolicyString] = frozenset()
    reason: NonEmptyPolicyString

    @model_validator(mode="after")
    def validate_policy_shape(self) -> Self:
        """Keep executable policy explicit and fail closed on ambiguous shapes."""
        if self.authority_level not in {
            AuthorityLevel.POLICY,
            AuthorityLevel.MANDATORY_CONTROL,
        }:
            raise ValueError("executable policy requires policy or mandatory_control authority")

        if self.target_domains is not None and not self.target_domains:
            raise ValueError("target_domains cannot be explicitly empty")

        if self.effect is PolicyEffect.NARROW:
            if self.allowed_keys is None and not self.redact_keys:
                raise ValueError("narrow policy requires allowed_keys and/or redact_keys")
        elif self.allowed_keys is not None or self.redact_keys:
            raise ValueError("allow/deny policy cannot carry key narrowing fields")

        return self


class PolicyEvaluationRequest(BaseModel):
    """Requested context surface presented to the policy engine."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: NonEmptyPolicyString
    requested_domains: frozenset[ContextDomain]
    requested_keys: frozenset[NonEmptyPolicyString] | None = None


class PolicyDomainDecision(BaseModel):
    """Admission result for one requested context domain."""

    model_config = ConfigDict(extra="forbid")

    domain: ContextDomain
    allowed: bool
    decisive_rule_ids: tuple[str, ...]
    reason: str


class PolicyDecision(BaseModel):
    """Policy result passed to later retrieval/runtime layers."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    decision: PolicyDecisionKind
    allowed_domains: frozenset[ContextDomain]
    denied_domains: frozenset[ContextDomain]
    allowed_keys: frozenset[str] | None
    redacted_keys: frozenset[str]
    domain_decisions: tuple[PolicyDomainDecision, ...]
    narrowing_rule_ids: tuple[str, ...]
