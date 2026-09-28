"""SQLAlchemy model for immutable context-resolution audit records."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from contextplane.persistence.base import Base


class ResolutionAuditRecord(Base):
    """Append-only audit record for one authenticated resolve attempt."""

    __tablename__ = "resolution_audit"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_resolution_audit_tenant_nonempty",
        ),
        CheckConstraint(
            "length(btrim(principal_subject)) > 0",
            name="ck_resolution_audit_subject_nonempty",
        ),
        CheckConstraint(
            "principal_kind IN ('user','agent','service')",
            name="ck_resolution_audit_principal_kind",
        ),
        CheckConstraint(
            "outcome IN ('allowed','narrowed','denied','conflict','policy_error')",
            name="ck_resolution_audit_outcome",
        ),
        CheckConstraint(
            "requested_key_count >= 0",
            name="ck_resolution_audit_requested_key_count_nonnegative",
        ),
    )

    resolution_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    principal_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    principal_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    requested_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    requested_key_count: Mapped[int] = mapped_column(nullable=False)
    selector_dimensions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    policy_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    denied_domains: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    policy_rule_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)

    considered_record_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    returned_items: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False)
    conflict_steps: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)

    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(512), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
