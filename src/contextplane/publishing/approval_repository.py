"""Persistence helpers for high-authority publication proposals and events."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.auth import Principal
from contextplane.publishing.approval_db import (
    PublicationApprovalEventRecord,
    PublicationProposalRecord,
)
from contextplane.publishing.domain import (
    ApprovalEventOutcome,
    ApprovalEventType,
    PublicationApprovalPermission,
)


def get_proposal_by_actor_idempotency(
    session: Session,
    *,
    principal: Principal,
    idempotency_key_hash: str,
) -> PublicationProposalRecord | None:
    """Return an actor-scoped draft for idempotent proposal replay."""
    client_predicate = (
        PublicationProposalRecord.publisher_client_id.is_(None)
        if principal.client_id is None
        else PublicationProposalRecord.publisher_client_id == principal.client_id
    )
    return session.scalar(
        select(PublicationProposalRecord).where(
            PublicationProposalRecord.tenant_id == principal.tenant_id,
            PublicationProposalRecord.publisher_kind == principal.kind.value,
            PublicationProposalRecord.publisher_subject == principal.subject,
            client_predicate,
            PublicationProposalRecord.idempotency_key_hash == idempotency_key_hash,
        )
    )


def get_proposal(
    session: Session,
    *,
    tenant_id: str,
    proposal_id: UUID,
    for_update: bool = False,
) -> PublicationProposalRecord | None:
    """Return one tenant-scoped proposal, optionally locking it."""
    statement = select(PublicationProposalRecord).where(
        PublicationProposalRecord.tenant_id == tenant_id,
        PublicationProposalRecord.proposal_id == proposal_id,
    )
    if for_update:
        statement = statement.with_for_update()
    return session.scalar(statement)


def get_successful_event(
    session: Session,
    *,
    tenant_id: str,
    proposal_id: UUID,
    event_type: ApprovalEventType,
) -> PublicationApprovalEventRecord | None:
    """Return the successful immutable event for one lifecycle step."""
    return session.scalar(
        select(PublicationApprovalEventRecord)
        .where(
            PublicationApprovalEventRecord.tenant_id == tenant_id,
            PublicationApprovalEventRecord.proposal_id == proposal_id,
            PublicationApprovalEventRecord.event_type == event_type.value,
            PublicationApprovalEventRecord.outcome
            == ApprovalEventOutcome.SUCCEEDED.value,
        )
        .order_by(PublicationApprovalEventRecord.created_at.asc())
        .limit(1)
    )


def create_approval_event(
    session: Session,
    *,
    principal: Principal,
    proposal_id: UUID,
    event_type: ApprovalEventType,
    outcome: ApprovalEventOutcome,
    permission_used: PublicationApprovalPermission | None = None,
    context_record_id: UUID | None = None,
    logical_id: UUID | None = None,
    version: int | None = None,
    error_code: str | None = None,
) -> PublicationApprovalEventRecord:
    """Append one immutable workflow attempt."""
    event = PublicationApprovalEventRecord(
        proposal_id=proposal_id,
        tenant_id=principal.tenant_id,
        event_type=event_type.value,
        actor_kind=principal.kind.value,
        actor_subject=principal.subject,
        actor_client_id=principal.client_id,
        permission_used=permission_used.value if permission_used is not None else None,
        outcome=outcome.value,
        context_record_id=context_record_id,
        logical_id=logical_id,
        version=version,
        error_code=error_code,
    )
    session.add(event)
    session.flush()
    return event
