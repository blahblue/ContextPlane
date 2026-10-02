"""Append-only audit model for authenticated context publication."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from contextplane.persistence.base import Base


class PublicationAuditRecord(Base):
    """Payload-minimized immutable record for one publish attempt."""

    __tablename__ = "publication_audit"
    __table_args__ = (
        CheckConstraint("length(btrim(tenant_id)) > 0", name="ck_publication_audit_tenant"),
        CheckConstraint("length(btrim(principal_subject)) > 0", name="ck_publication_audit_subject"),
        CheckConstraint(
            "principal_kind IN ('user','agent','service')",
            name="ck_publication_audit_principal_kind",
        ),
        CheckConstraint(
            "action IN ('create','supersede')",
            name="ck_publication_audit_action",
        ),
        CheckConstraint(
            "authority_level IN ('preference','recommendation','standard','policy','mandatory_control')",
            name="ck_publication_audit_authority",
        ),
        CheckConstraint(
            "outcome IN ('succeeded','denied','conflict')",
            name="ck_publication_audit_outcome",
        ),
        CheckConstraint(
            "idempotency_key_hash ~ '^[0-9a-f]{64}$'",
            name="ck_publication_audit_idempotency_hash",
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_publication_audit_request_hash",
        ),
        CheckConstraint(
            "key_hash ~ '^[0-9a-f]{64}$'",
            name="ck_publication_audit_key_hash",
        ),
    )

    publication_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    principal_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(512), nullable=True)

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(64), nullable=False)
    permission_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    previous_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    context_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    logical_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    version: Mapped[int | None] = mapped_column(nullable=True)

    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
