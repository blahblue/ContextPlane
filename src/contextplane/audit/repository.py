"""Insert-only persistence operations for resolution audit records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.audit.db import ResolutionAuditRecord
from contextplane.audit.domain import ResolutionAuditCreate


def create_resolution_audit(
    session: Session,
    audit: ResolutionAuditCreate,
) -> ResolutionAuditRecord:
    """Insert one immutable audit record without committing the caller transaction."""
    record = ResolutionAuditRecord(
        resolution_id=audit.resolution_id,
        tenant_id=audit.tenant_id,
        principal_kind=audit.principal_kind.value,
        principal_subject=audit.principal_subject,
        client_id=audit.client_id,
        as_of=audit.as_of,
        requested_domains=[domain.value for domain in audit.requested_domains],
        requested_key_count=audit.requested_key_count,
        selector_dimensions=list(audit.selector_dimensions),
        policy_decision=(
            audit.policy_decision.value if audit.policy_decision is not None else None
        ),
        allowed_domains=[domain.value for domain in audit.allowed_domains],
        denied_domains=[domain.value for domain in audit.denied_domains],
        policy_rule_ids=list(audit.policy_rule_ids),
        considered_record_ids=[str(item) for item in audit.considered_record_ids],
        returned_items=[
            {
                "record_id": str(item.record_id),
                "logical_id": str(item.logical_id),
                "domain": item.domain.value,
                "version": item.version,
            }
            for item in audit.returned_items
        ],
        conflict_steps=[
            {
                "winner_record_id": str(step.winner_record_id),
                "suppressed_record_id": str(step.suppressed_record_id),
            }
            for step in audit.conflict_steps
        ],
        outcome=audit.outcome.value,
        error_code=audit.error_code,
    )
    session.add(record)
    session.flush()
    return record


def get_resolution_audit(
    session: Session,
    *,
    tenant_id: str,
    resolution_id: UUID,
) -> ResolutionAuditRecord | None:
    """Return one audit record only inside the requested tenant boundary."""
    return session.scalar(
        select(ResolutionAuditRecord).where(
            ResolutionAuditRecord.tenant_id == tenant_id,
            ResolutionAuditRecord.resolution_id == resolution_id,
        )
    )
