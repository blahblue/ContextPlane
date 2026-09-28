"""Persistence model for tenant context revision state."""

from sqlalchemy import BigInteger, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from contextplane.persistence.base import Base


class ContextStateRevisionRecord(Base):
    """Monotonic tenant revision bumped by context-item database mutations."""

    __tablename__ = "context_state_revisions"
    __table_args__ = (
        CheckConstraint(
            "length(btrim(tenant_id)) > 0",
            name="ck_context_state_revision_tenant_nonempty",
        ),
        CheckConstraint(
            "revision >= 0",
            name="ck_context_state_revision_nonnegative",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(512), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
