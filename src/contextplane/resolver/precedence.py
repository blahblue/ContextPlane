"""Deterministic conflict precedence for resolved context candidates."""

from collections import defaultdict
from dataclasses import dataclass

from contextplane.context_registry.domain import AuthorityLevel, OverridePolicy
from contextplane.resolver.domain import (
    ConflictDecision,
    ContextCandidate,
    ContextResolutionResult,
    EffectiveContextResult,
)

_AUTHORITY_RANK = {
    AuthorityLevel.PREFERENCE: 1,
    AuthorityLevel.RECOMMENDATION: 2,
    AuthorityLevel.STANDARD: 3,
    AuthorityLevel.POLICY: 4,
    AuthorityLevel.MANDATORY_CONTROL: 5,
}


class ContextPrecedenceConflictError(RuntimeError):
    """Raised when equally ranked conflicting context cannot be safely resolved."""


@dataclass(frozen=True)
class _Comparison:
    winner: ContextCandidate
    loser: ContextCandidate
    reason: str


def _same_payload(left: ContextCandidate, right: ContextCandidate) -> bool:
    """Return whether two candidates carry equivalent payload semantics."""
    return left.value == right.value and left.payload_ref == right.payload_ref


def _compare(
    current: ContextCandidate,
    challenger: ContextCandidate,
) -> _Comparison:
    """Apply authority, scope specificity, and override semantics."""
    current_rank = _AUTHORITY_RANK[current.authority_level]
    challenger_rank = _AUTHORITY_RANK[challenger.authority_level]

    if challenger.specificity == current.specificity:
        if challenger_rank > current_rank:
            return _Comparison(
                winner=challenger,
                loser=current,
                reason="higher authority at equal scope specificity",
            )
        if challenger_rank < current_rank:
            return _Comparison(
                winner=current,
                loser=challenger,
                reason="higher authority at equal scope specificity",
            )

        if _same_payload(current, challenger):
            winner, loser = sorted(
                (current, challenger),
                key=lambda candidate: str(candidate.record_id),
            )
            return _Comparison(
                winner=winner,
                loser=loser,
                reason="equivalent payload at equal precedence; deterministically deduplicated",
            )

        raise ContextPrecedenceConflictError(
            "conflicting context has equal authority and scope specificity "
            f"for key '{current.key}'"
        )

    if challenger.specificity < current.specificity:
        raise ValueError("precedence comparison requires nondecreasing specificity")

    if challenger.authority_level is AuthorityLevel.MANDATORY_CONTROL:
        return _Comparison(
            winner=challenger,
            loser=current,
            reason="mandatory control overrides lower authority context",
        )

    if current.authority_level is AuthorityLevel.MANDATORY_CONTROL:
        return _Comparison(
            winner=current,
            loser=challenger,
            reason="mandatory control cannot be overridden by narrower context",
        )

    if challenger_rank > current_rank:
        return _Comparison(
            winner=challenger,
            loser=current,
            reason="narrower context also has higher authority",
        )

    if current.override_policy is OverridePolicy.ALLOW:
        return _Comparison(
            winner=challenger,
            loser=current,
            reason="broader context explicitly allows narrower override",
        )

    return _Comparison(
        winner=current,
        loser=challenger,
        reason="broader context denies narrower override",
    )


def _resolve_key_group(
    key: str,
    candidates: list[ContextCandidate],
) -> tuple[ContextCandidate, ConflictDecision]:
    """Choose one effective value for a key or fail on an unsafe exact tie."""
    ordered = sorted(
        candidates,
        key=lambda candidate: (
            candidate.specificity,
            _AUTHORITY_RANK[candidate.authority_level],
            str(candidate.record_id),
        ),
    )

    winner = ordered[0]
    suppressed: list[ContextCandidate] = []
    reasons: list[str] = []

    for challenger in ordered[1:]:
        comparison = _compare(winner, challenger)
        winner = comparison.winner
        suppressed.append(comparison.loser)
        reasons.append(comparison.reason)

    return winner, ConflictDecision(
        key=key,
        winner_record_id=winner.record_id,
        suppressed_record_ids=tuple(
            sorted(
                (candidate.record_id for candidate in suppressed),
                key=str,
            )
        ),
        reasons=tuple(reasons),
    )


def apply_conflict_precedence(
    resolution: ContextResolutionResult,
) -> EffectiveContextResult:
    """Collapse candidate conflicts into one effective item per context key."""
    grouped: dict[str, list[ContextCandidate]] = defaultdict(list)
    for candidate in resolution.candidates:
        grouped[candidate.key].append(candidate)

    effective: list[ContextCandidate] = []
    decisions: list[ConflictDecision] = []

    for key in sorted(grouped):
        winner, decision = _resolve_key_group(key, grouped[key])
        effective.append(winner)
        decisions.append(decision)

    return EffectiveContextResult(
        tenant_id=resolution.tenant_id,
        as_of=resolution.as_of,
        effective=tuple(effective),
        decisions=tuple(decisions),
    )
