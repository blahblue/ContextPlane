"""Persistence helpers for immutable publication audit records."""

from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from contextplane.auth import Principal
from contextplane.publishing.db import PublicationAuditRecord
from contextplane.publishing.domain import (
    PublicationAction,
    PublicationAuthorization,
    PublicationOutcome,
)


def get_publication_audit_by_idempotency(
    session: Session,
    *,
    principal: Principal,
    idempotency_key_hash: str,
) -> PublicationAuditRecord | None:
    """Return an actor-scoped publication audit for idempotent replay."""
    client_predicate = (
        PublicationAuditRecord.client_id.is_(None)
        if principal.client_id is None
        else PublicationAuditRecord.client_id == principal.client_id
    )
    return session.scalar(
        select(PublicationAuditRecord).where(
            PublicationAuditRecord.tenant_id == principal.tenant_id,
            PublicationAuditRecord.principal_kind == principal.kind.value,
            PublicationAuditRecord.principal_subject == principal.subject,
            client_predicate,
            PublicationAuditRecord.idempotency_key_hash == idempotency_key_hash,
        )
    )


def create_publication_audit(
    session: Session,
    *,
    principal: Principal,
    action: PublicationAction,
    authority_level: str,
    idempotency_key_hash: str,
    request_hash: str,
    key_hash: str,
    outcome: PublicationOutcome,
    authorization: PublicationAuthorization | None = None,
    previous_record_id: UUID | None = None,
    context_record_id: UUID | None = None,
    logical_id: UUID | None = None,
    version: int | None = None,
    error_code: str | None = None,
) -> PublicationAuditRecord:
    """Insert one payload-minimized immutable publication audit."""
    record = PublicationAuditRecord(
        tenant_id=principal.tenant_id,
        principal_kind=principal.kind.value,
        principal_subject=principal.subject,
        client_id=principal.client_id,
        action=action.value,
        authority_level=authority_level,
        permission_used=(
            authorization.permission_used.value if authorization is not None else None
        ),
        idempotency_key_hash=idempotency_key_hash,
        request_hash=request_hash,
        key_hash=key_hash,
        previous_record_id=previous_record_id,
        context_record_id=context_record_id,
        logical_id=logical_id,
        version=version,
        outcome=outcome.value,
        error_code=error_code,
    )
    session.add(record)
    session.flush()
    return record
