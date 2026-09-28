"""Deterministic tenant-scoped context candidate resolution."""

from collections.abc import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from contextplane.context_registry.db import ContextItemRecord
from contextplane.resolver.domain import (
    CandidateExplanation,
    ContextCandidate,
    ContextResolutionRequest,
    ContextResolutionResult,
)

_SCOPE_FIELDS = (
    "business_unit",
    "team",
    "role",
    "user_id",
    "agent_id",
    "application",
    "repository",
    "resource",
    "task",
    "audience",
    "environment",
)


def _latest_active_versions(
    records: Iterable[ContextItemRecord],
) -> list[ContextItemRecord]:
    """Keep only the highest active version of each logical item."""
    selected: dict[object, ContextItemRecord] = {}
    for record in records:
        selected.setdefault(record.logical_id, record)
    return list(selected.values())


def _scope_match(
    record: ContextItemRecord,
    request: ContextResolutionRequest,
) -> tuple[bool, tuple[str, ...]]:
    """Match explicit item scope dimensions; null item dimensions are wildcards."""
    matched: list[str] = []
    request_scope = request.scope

    for field in _SCOPE_FIELDS:
        required = getattr(record, field)
        if required is None:
            continue

        actual = getattr(request_scope, field)
        if actual != required:
            return False, ()
        matched.append(field)

    return True, tuple(matched)


def resolve_context_candidates(
    session: Session,
    request: ContextResolutionRequest,
) -> ContextResolutionResult:
    """Resolve applicable immutable context candidates without choosing key winners."""
    query = (
        select(ContextItemRecord)
        .where(
            ContextItemRecord.tenant_id == request.scope.tenant_id,
            ContextItemRecord.effective_from <= request.as_of,
            or_(
                ContextItemRecord.effective_to.is_(None),
                ContextItemRecord.effective_to > request.as_of,
            ),
        )
        .order_by(
            ContextItemRecord.logical_id.asc(),
            ContextItemRecord.version.desc(),
        )
    )

    if request.domains:
        query = query.where(
            ContextItemRecord.domain.in_([domain.value for domain in request.domains])
        )

    active_versions = _latest_active_versions(session.scalars(query))

    candidates: list[ContextCandidate] = []
    explanations: list[CandidateExplanation] = []

    for record in active_versions:
        matches, matched_dimensions = _scope_match(record, request)
        if not matches:
            continue

        specificity = len(matched_dimensions)
        candidate = ContextCandidate(
            logical_id=record.logical_id,
            record_id=record.id,
            key=record.key,
            value=record.value,
            payload_ref=record.payload_ref,
            domain=record.domain,
            authority_level=record.authority_level,
            sensitivity=record.sensitivity,
            override_policy=record.override_policy,
            version=record.version,
            specificity=specificity,
            matched_dimensions=matched_dimensions,
        )
        candidates.append(candidate)
        explanations.append(
            CandidateExplanation(
                logical_id=record.logical_id,
                record_id=record.id,
                version=record.version,
                matched_dimensions=matched_dimensions,
                specificity=specificity,
                reason=(
                    "selected latest active logical version and matched all explicit "
                    "context scope dimensions"
                ),
            )
        )

    order = sorted(
        range(len(candidates)),
        key=lambda index: (
            candidates[index].key,
            -candidates[index].specificity,
            str(candidates[index].logical_id),
        ),
    )

    return ContextResolutionResult(
        tenant_id=request.scope.tenant_id,
        as_of=request.as_of,
        candidates=tuple(candidates[index] for index in order),
        explanations=tuple(explanations[index] for index in order),
    )
