"""SQLAlchemy persistence model for context items."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from contextplane.persistence.base import Base


class ContextItemRecord(Base):
    """Persisted organizational context item."""

    __tablename__ = "context_items"
    __table_args__ = (
        CheckConstraint("version > 0", name="ck_context_items_version_positive"),
        CheckConstraint(
            "(value IS NOT NULL) <> (payload_ref IS NOT NULL)",
            name="ck_context_items_exactly_one_payload",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to > effective_from",
            name="ck_context_items_effective_window",
        ),
        CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_context_items_tenant_nonempty",
        ),
        CheckConstraint("length(btrim(key)) > 0", name="ck_context_items_key_nonempty"),
        CheckConstraint("length(btrim(owner)) > 0", name="ck_context_items_owner_nonempty"),
        CheckConstraint(
            "length(btrim(source_identifier)) > 0",
            name="ck_context_items_source_identifier_nonempty",
        ),
        CheckConstraint(
            "checksum ~ '^[0-9a-f]{64}$'",
            name="ck_context_items_checksum_sha256",
        ),
        CheckConstraint(
            "domain IN ('brand','presentation','engineering','security')",
            name="ck_context_items_domain",
        ),
        CheckConstraint(
            "authority_level IN "
            "('preference','recommendation','standard','policy','mandatory_control')",
            name="ck_context_items_authority",
        ),
        CheckConstraint(
            "sensitivity IN ('public','internal','confidential','restricted')",
            name="ck_context_items_sensitivity",
        ),
        CheckConstraint(
            "override_policy IN ('allow','deny')",
            name="ck_context_items_override_policy",
        ),
        CheckConstraint(
            "source_type IN "
            "('manual','git','sharepoint','google_drive','databricks','fabric','api')",
            name="ck_context_items_source_type",
        ),
        Index("ix_context_items_tenant_key", "tenant_id", "key"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    key: Mapped[str] = mapped_column(String(512), nullable=False)
    value: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    payload_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False)

    tenant_id: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    business_unit: Mapped[str | None] = mapped_column(String(512), nullable=True)
    team: Mapped[str | None] = mapped_column(String(512), nullable=True)
    role: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    agent_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    application: Mapped[str | None] = mapped_column(String(512), nullable=True)
    repository: Mapped[str | None] = mapped_column(String(512), nullable=True)
    resource: Mapped[str | None] = mapped_column(String(512), nullable=True)
    task: Mapped[str | None] = mapped_column(String(512), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(512), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(512), nullable=True)

    owner: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_identifier: Mapped[str] = mapped_column(String(512), nullable=False)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)

    authority_level: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sensitivity: Mapped[str] = mapped_column(String(64), nullable=False)
    override_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
