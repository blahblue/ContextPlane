"""Persistence models for immutable high-authority publication workflow."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from contextplane.persistence.base import Base


class PublicationProposalRecord(Base):
    """Immutable high-authority draft proposal."""

    __tablename__ = "publication_proposals"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_publication_proposals_tenant",
        ),
        CheckConstraint(
            "length(btrim(publisher_subject)) > 0",
            name="ck_publication_proposals_subject",
        ),
        CheckConstraint(
            "publisher_kind IN ('user','agent','service')",
            name="ck_publication_proposals_kind",
        ),
        CheckConstraint(
            "action IN ('create','supersede')",
            name="ck_publication_proposals_action",
        ),
        CheckConstraint(
            "authority_level IN ('policy','mandatory_control')",
            name="ck_publication_proposals_authority",
        ),
        CheckConstraint(
            "publication_permission IN "
            "('context.publish.policy','context.publish.mandatory_control')",
            name="ck_publication_proposals_permission",
        ),
        CheckConstraint(
            "(action = 'create' AND previous_record_id IS NULL) OR "
            "(action = 'supersede' AND previous_record_id IS NOT NULL)",
            name="ck_publication_proposals_previous_shape",
        ),
        CheckConstraint(
            "idempotency_key_hash ~ '^[0-9a-f]{64}$'",
            name="ck_publication_proposals_idempotency_hash",
        ),
        CheckConstraint(
            "request_hash ~ '^[0-9a-f]{64}$'",
            name="ck_publication_proposals_request_hash",
        ),
        UniqueConstraint(
            "tenant_id",
            "proposal_id",
            name="uq_publication_proposals_tenant_id",
        ),
    )

    proposal_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    tenant_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    publisher_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    publisher_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    publisher_client_id: Mapped[str | None] = mapped_column(String(512), nullable=True)

    action: Mapped[str] = mapped_column(String(32), nullable=False)
    authority_level: Mapped[str] = mapped_column(String(64), nullable=False)
    publication_permission: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_record_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )

    item_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PublicationApprovalEventRecord(Base):
    """Append-only approval/activation attempt for one proposal."""

    __tablename__ = "publication_approval_events"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_publication_approval_events_tenant",
        ),
        CheckConstraint(
            "length(btrim(actor_subject)) > 0",
            name="ck_publication_approval_events_subject",
        ),
        CheckConstraint(
            "actor_kind IN ('user','agent','service')",
            name="ck_publication_approval_events_kind",
        ),
        CheckConstraint(
            "event_type IN ('approve','activate')",
            name="ck_publication_approval_events_type",
        ),
        CheckConstraint(
            "outcome IN ('succeeded','denied','conflict')",
            name="ck_publication_approval_events_outcome",
        ),
        CheckConstraint(
            "permission_used IS NULL OR permission_used IN ("
            "'context.approve.policy',"
            "'context.approve.mandatory_control',"
            "'context.activate.policy',"
            "'context.activate.mandatory_control'"
            ")",
            name="ck_publication_approval_events_permission",
        ),
        CheckConstraint(
            "("
            "event_type = 'approve' AND context_record_id IS NULL "
            "AND logical_id IS NULL AND version IS NULL"
            ") OR ("
            "event_type = 'activate'"
            ")",
            name="ck_publication_approval_events_type_shape",
        ),
        CheckConstraint(
            "("
            "event_type = 'activate' AND outcome = 'succeeded' "
            "AND context_record_id IS NOT NULL AND logical_id IS NOT NULL "
            "AND version IS NOT NULL AND version > 0 AND error_code IS NULL"
            ") OR ("
            "event_type = 'approve' AND outcome = 'succeeded' "
            "AND error_code IS NULL"
            ") OR ("
            "outcome IN ('denied','conflict') AND error_code IS NOT NULL "
            "AND context_record_id IS NULL AND logical_id IS NULL "
            "AND version IS NULL"
            ")",
            name="ck_publication_approval_events_outcome_shape",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "proposal_id"],
            [
                "publication_proposals.tenant_id",
                "publication_proposals.proposal_id",
            ],
            name="fk_publication_approval_events_tenant_proposal",
        ),
    )

    event_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    proposal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_subject: Mapped[str] = mapped_column(String(512), nullable=False)
    actor_client_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    permission_used: Mapped[str | None] = mapped_column(String(128), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)

    context_record_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )
    logical_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    version: Mapped[int | None] = mapped_column(nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
