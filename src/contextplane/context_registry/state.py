"""Read tenant context revision and effective-time transition state."""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.state_db import ContextStateRevisionRecord


@dataclass(frozen=True)
class ContextStateSnapshot:
    """Version token and next time boundary for safe resolution caching."""

    revision: int
    next_transition: datetime | None


def get_context_state_snapshot(
    session: Session,
    *,
    tenant_id: str,
    as_of: datetime,
) -> ContextStateSnapshot:
    """Return a tenant revision plus its next potential effective-time change."""
    revision = session.scalar(
        select(ContextStateRevisionRecord.revision).where(
            ContextStateRevisionRecord.tenant_id == tenant_id
        )
    )
    transition = session.execute(
        select(
            func.min(ContextItemRecord.effective_from).filter(
                ContextItemRecord.effective_from > as_of
            ),
            func.min(ContextItemRecord.effective_to).filter(
                ContextItemRecord.effective_to.is_not(None),
                ContextItemRecord.effective_to > as_of,
            ),
        ).where(ContextItemRecord.tenant_id == tenant_id)
    ).one()

    future_start, future_end = transition
    candidates = [
        value for value in (future_start, future_end) if value is not None
    ]

    return ContextStateSnapshot(
        revision=0 if revision is None else revision,
        next_transition=min(candidates) if candidates else None,
    )
