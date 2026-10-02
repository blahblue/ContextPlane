"""SQLAlchemy persistence model for context items."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from contextplane.persistence.base import Base


class ContextItemRecord(Base):
    """Persisted immutable version of an organizational context item."""

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
        CheckConstraint(
            "supersedes_id IS NULL OR supersedes_id <> id",
            name="ck_context_items_no_self_supersession",
        ),
        CheckConstraint(
            "("
            "publisher_subject IS NULL AND publisher_kind IS NULL "
            "AND publication_action IS NULL AND publication_permission IS NULL"
            ") OR ("
            "publisher_subject IS NOT NULL AND length(btrim(publisher_subject)) > 0 "
            "AND publisher_kind IN ('user','agent','service') "
            "AND publication_action IN ('create','supersede') "
            "AND publication_permission IN ("
            "'context.publish.preference.self',"
            "'context.publish.preference',"
            "'context.publish.recommendation',"
            "'context.publish.standard',"
            "'context.publish.policy',"
            "'context.publish.mandatory_control'"
            ")"
            ")",
            name="ck_context_items_publication_provenance_shape",
        ),
        CheckConstraint(
            "(version = 1 AND supersedes_id IS NULL) OR "
            "(version > 1 AND supersedes_id IS NOT NULL)",
            name="ck_context_items_version_lineage_shape",
        ),
        UniqueConstraint(
            "tenant_id",
            "logical_id",
            "version",
            name="uq_context_items_tenant_logical_version",
        ),
        UniqueConstraint(
            "tenant_id",
            "logical_id",
            "id",
            name="uq_context_items_tenant_logical_id",
        ),
        UniqueConstraint("supersedes_id", name="uq_context_items_supersedes_id"),
        ForeignKeyConstraint(
            ["tenant_id", "logical_id", "supersedes_id"],
            ["context_items.tenant_id", "context_items.logical_id", "context_items.id"],
            name="fk_context_items_supersedes_same_logical_item",
            ondelete="RESTRICT",
        ),
        Index("ix_context_items_tenant_key", "tenant_id", "key"),
        Index("ix_context_items_tenant_logical", "tenant_id", "logical_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    logical_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        default=uuid4,
    )
    supersedes_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
    )

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

    publisher_subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    publisher_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publisher_client_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    publication_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    publication_permission: Mapped[str | None] = mapped_column(String(128), nullable=True)

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
