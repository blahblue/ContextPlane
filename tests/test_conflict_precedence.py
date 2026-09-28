from datetime import UTC, datetime
from uuid import UUID

import pytest

from contextplane.context_registry import (
    AuthorityLevel,
    ContextDomain,
    OverridePolicy,
    SensitivityLevel,
)
from contextplane.resolver import (
    ContextCandidate,
    ContextPrecedenceConflictError,
    ContextResolutionResult,
    apply_conflict_precedence,
)

NOW = datetime(2026, 9, 28, 16, 0, tzinfo=UTC)


def candidate(
    *,
    record: int,
    key: str = "engineering.rule",
    authority: AuthorityLevel,
    specificity: int,
    override: OverridePolicy,
    value: str,
) -> ContextCandidate:
    return ContextCandidate(
        logical_id=UUID(int=record + 100),
        record_id=UUID(int=record),
        key=key,
        value={"value": value},
        payload_ref=None,
        domain=ContextDomain.ENGINEERING,
        authority_level=authority,
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=override,
        version=1,
        specificity=specificity,
        matched_dimensions=tuple(f"d{i}" for i in range(specificity)),
    )


def resolve(*candidates: ContextCandidate) -> ContextResolutionResult:
    return ContextResolutionResult(
        tenant_id="acme",
        as_of=NOW,
        candidates=tuple(candidates),
        explanations=(),
    )


@pytest.mark.parametrize(
    ("broad", "narrow", "expected"),
    [
        (
            candidate(
                record=1,
                authority=AuthorityLevel.STANDARD,
                specificity=0,
                override=OverridePolicy.DENY,
                value="broad",
            ),
            candidate(
                record=2,
                authority=AuthorityLevel.PREFERENCE,
                specificity=1,
                override=OverridePolicy.DENY,
                value="narrow",
            ),
            1,
        ),
        (
            candidate(
                record=3,
                authority=AuthorityLevel.STANDARD,
                specificity=0,
                override=OverridePolicy.ALLOW,
                value="broad",
            ),
            candidate(
                record=4,
                authority=AuthorityLevel.PREFERENCE,
                specificity=1,
                override=OverridePolicy.DENY,
                value="narrow",
            ),
            4,
        ),
        (
            candidate(
                record=5,
                authority=AuthorityLevel.PREFERENCE,
                specificity=0,
                override=OverridePolicy.DENY,
                value="broad",
            ),
            candidate(
                record=6,
                authority=AuthorityLevel.POLICY,
                specificity=1,
                override=OverridePolicy.DENY,
                value="narrow",
            ),
            6,
        ),
        (
            candidate(
                record=7,
                authority=AuthorityLevel.MANDATORY_CONTROL,
                specificity=0,
                override=OverridePolicy.ALLOW,
                value="broad",
            ),
            candidate(
                record=8,
                authority=AuthorityLevel.POLICY,
                specificity=3,
                override=OverridePolicy.ALLOW,
                value="narrow",
            ),
            7,
        ),
    ],
)
def test_scope_override_matrix(
    broad: ContextCandidate,
    narrow: ContextCandidate,
    expected: int,
) -> None:
    result = apply_conflict_precedence(resolve(broad, narrow))

    assert result.effective[0].record_id == UUID(int=expected)


def test_higher_authority_wins_at_equal_specificity() -> None:
    lower = candidate(
        record=9,
        authority=AuthorityLevel.RECOMMENDATION,
        specificity=2,
        override=OverridePolicy.DENY,
        value="lower",
    )
    higher = candidate(
        record=10,
        authority=AuthorityLevel.STANDARD,
        specificity=2,
        override=OverridePolicy.ALLOW,
        value="higher",
    )

    result = apply_conflict_precedence(resolve(lower, higher))

    assert result.effective[0].record_id == higher.record_id


def test_equal_precedence_conflicting_payload_fails_closed() -> None:
    left = candidate(
        record=11,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.DENY,
        value="left",
    )
    right = candidate(
        record=12,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.ALLOW,
        value="right",
    )

    with pytest.raises(ContextPrecedenceConflictError, match="equal authority"):
        apply_conflict_precedence(resolve(left, right))


def test_equal_precedence_equivalent_payload_is_deduplicated_deterministically() -> None:
    left = candidate(
        record=13,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.DENY,
        value="same",
    )
    right = candidate(
        record=14,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.DENY,
        value="same",
    )

    result = apply_conflict_precedence(resolve(right, left))

    assert result.effective[0].record_id == left.record_id
    assert result.decisions[0].steps[0].suppressed_record_id == right.record_id


def test_multiple_keys_produce_one_effective_item_per_key() -> None:
    first = candidate(
        record=15,
        key="a.key",
        authority=AuthorityLevel.STANDARD,
        specificity=0,
        override=OverridePolicy.DENY,
        value="a",
    )
    second = candidate(
        record=16,
        key="b.key",
        authority=AuthorityLevel.STANDARD,
        specificity=0,
        override=OverridePolicy.DENY,
        value="b",
    )

    result = apply_conflict_precedence(resolve(second, first))

    assert [item.key for item in result.effective] == ["a.key", "b.key"]
    assert [decision.key for decision in result.decisions] == ["a.key", "b.key"]


def test_decision_records_suppressed_context_and_reason() -> None:
    broad = candidate(
        record=17,
        authority=AuthorityLevel.STANDARD,
        specificity=0,
        override=OverridePolicy.DENY,
        value="broad",
    )
    narrow = candidate(
        record=18,
        authority=AuthorityLevel.PREFERENCE,
        specificity=2,
        override=OverridePolicy.DENY,
        value="narrow",
    )

    result = apply_conflict_precedence(resolve(broad, narrow))
    decision = result.decisions[0]

    assert decision.winner_record_id == broad.record_id
    assert decision.steps[0].winner_record_id == broad.record_id
    assert decision.steps[0].suppressed_record_id == narrow.record_id
    assert decision.steps[0].reason == "broader context denies narrower override"


def test_equal_payload_with_different_override_policy_is_still_a_conflict() -> None:
    allow = candidate(
        record=19,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.ALLOW,
        value="same",
    )
    deny = candidate(
        record=20,
        authority=AuthorityLevel.STANDARD,
        specificity=1,
        override=OverridePolicy.DENY,
        value="same",
    )

    with pytest.raises(ContextPrecedenceConflictError, match="equal authority"):
        apply_conflict_precedence(resolve(allow, deny))


def test_multi_candidate_chain_preserves_each_suppression_reason() -> None:
    broad = candidate(
        record=21,
        authority=AuthorityLevel.STANDARD,
        specificity=0,
        override=OverridePolicy.ALLOW,
        value="broad",
    )
    team = candidate(
        record=22,
        authority=AuthorityLevel.PREFERENCE,
        specificity=1,
        override=OverridePolicy.DENY,
        value="team",
    )
    user_policy = candidate(
        record=23,
        authority=AuthorityLevel.POLICY,
        specificity=2,
        override=OverridePolicy.DENY,
        value="user-policy",
    )

    result = apply_conflict_precedence(resolve(user_policy, broad, team))
    decision = result.decisions[0]

    assert result.effective[0].record_id == user_policy.record_id
    assert len(decision.steps) == 2
    assert decision.steps[0].winner_record_id == team.record_id
    assert decision.steps[0].suppressed_record_id == broad.record_id
    assert decision.steps[1].winner_record_id == user_policy.record_id
    assert decision.steps[1].suppressed_record_id == team.record_id
