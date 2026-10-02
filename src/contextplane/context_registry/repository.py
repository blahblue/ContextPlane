"""Insert-only persistence operations for versioned context."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.domain import ContextItemCreate

if TYPE_CHECKING:
    from contextplane.publishing.domain import PublicationAuthorization


class ContextItemNotFoundError(LookupError):
    """Raised when a context item is not visible inside the requested tenant."""


class ContextVersionConflictError(RuntimeError):
    """Raised when a version can no longer be superseded safely."""


class ContextIdentityMismatchError(ValueError):
    """Raised when a replacement changes the logical key or domain."""


def _record_kwargs(item: ContextItemCreate) -> dict[str, object]:
    """Flatten a validated domain object into persistence fields."""
    scope = item.scope
    source = item.source

    return {
        "key": item.key,
        "value": item.value,
        "payload_ref": item.payload_ref,
        "domain": item.domain.value,
        "tenant_id": scope.tenant_id,
        "business_unit": scope.business_unit,
        "team": scope.team,
        "role": scope.role,
        "user_id": scope.user_id,
        "agent_id": scope.agent_id,
        "application": scope.application,
        "repository": scope.repository,
        "resource": scope.resource,
        "task": scope.task,
        "audience": scope.audience,
        "environment": scope.environment,
        "owner": item.owner,
        "source_type": source.type.value,
        "source_identifier": source.identifier,
        "source_uri": source.uri,
        "authority_level": item.authority_level.value,
        "effective_from": item.effective_from,
        "effective_to": item.effective_to,
        "sensitivity": item.sensitivity.value,
        "override_policy": item.override_policy.value,
        "checksum": item.checksum,
    }


def _publisher_kwargs(
    publication: "PublicationAuthorization | None",
) -> dict[str, object]:
    if publication is None:
        return {}
    return {
        "publisher_subject": publication.subject,
        "publisher_kind": publication.principal_kind.value,
        "publisher_client_id": publication.client_id,
        "publication_action": publication.action.value,
        "publication_permission": publication.permission_used.value,
    }


def create_context_item(
    session: Session,
    item: ContextItemCreate,
    *,
    publication: "PublicationAuthorization | None" = None,
) -> ContextItemRecord:
    """Insert the first immutable version of a logical context item."""
    record = ContextItemRecord(
        **_record_kwargs(item),
        **_publisher_kwargs(publication),
        version=1,
    )
    session.add(record)
    session.flush()
    return record


def supersede_context_item(
    session: Session,
    *,
    tenant_id: str,
    previous_id: UUID,
    replacement: ContextItemCreate,
    publication: "PublicationAuthorization | None" = None,
) -> ContextItemRecord:
    """Insert a new version while leaving the previous version untouched."""
    if replacement.scope.tenant_id != tenant_id:
        raise ContextIdentityMismatchError("replacement tenant does not match requested tenant")

    previous = session.scalar(
        select(ContextItemRecord)
        .where(
            ContextItemRecord.id == previous_id,
            ContextItemRecord.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if previous is None:
        raise ContextItemNotFoundError("context item was not found in the requested tenant")

    if replacement.key != previous.key or replacement.domain.value != previous.domain:
        raise ContextIdentityMismatchError(
            "replacement must preserve the logical context key and domain"
        )

    existing_successor = session.scalar(
        select(ContextItemRecord.id).where(ContextItemRecord.supersedes_id == previous.id)
    )
    if existing_successor is not None:
        raise ContextVersionConflictError("context item version has already been superseded")

    record = ContextItemRecord(
        **_record_kwargs(replacement),
        **_publisher_kwargs(publication),
        logical_id=previous.logical_id,
        supersedes_id=previous.id,
        version=previous.version + 1,
    )
    session.add(record)
    session.flush()
    return record


def get_context_history(
    session: Session,
    *,
    tenant_id: str,
    logical_id: UUID,
) -> list[ContextItemRecord]:
    """Return a tenant-scoped logical history ordered from oldest to newest."""
    return list(
        session.scalars(
            select(ContextItemRecord)
            .where(
                ContextItemRecord.tenant_id == tenant_id,
                ContextItemRecord.logical_id == logical_id,
            )
            .order_by(ContextItemRecord.version.asc())
        )
    )
