"""Authenticated immutable context publication runtime."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contextplane.auth import Principal
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.domain import AuthorityLevel
from contextplane.context_registry.repository import (
    ContextIdentityMismatchError,
    ContextItemNotFoundError,
    ContextVersionConflictError,
    create_context_item,
    supersede_context_item,
)
from contextplane.persistence.tenant import bind_session_tenant
from contextplane.publishing.build import (
    build_authenticated_context_item,
    publication_request_hash,
    sha256_text,
)
from contextplane.publishing.db import PublicationAuditRecord
from contextplane.publishing.domain import (
    PublicationAction,
    PublicationOutcome,
    PublicationPermission,
    PublishContextRequest,
    PublishContextResponse,
)
from contextplane.publishing.repository import (
    create_publication_audit,
    get_publication_audit_by_idempotency,
)
from contextplane.publishing.service import (
    PublicationAuthorizationError,
    authorize_publication,
)


class PublicationRuntimeError(RuntimeError):
    """Base class carrying a durable publication correlation identifier."""

    def __init__(
        self,
        message: str,
        *,
        publication_id: UUID | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.publication_id = publication_id
        self.error_code = error_code


class PublicationDeniedError(PublicationRuntimeError):
    """Authenticated principal is not authorized to publish requested authority."""


class PublicationConflictError(PublicationRuntimeError):
    """Publication conflicts with immutable version/idempotency invariants."""


class PublicationNotFoundError(PublicationRuntimeError):
    """Supersession target is not visible in the authenticated tenant."""


def _response_from_audit(
    *,
    audit_record: PublicationAuditRecord,
    context_record: ContextItemRecord,
) -> PublishContextResponse:
    if audit_record.permission_used is None:
        raise RuntimeError("successful publication audit is missing permission")
    return PublishContextResponse(
        publication_id=audit_record.publication_id,
        record_id=context_record.id,
        logical_id=context_record.logical_id,
        version=context_record.version,
        checksum=context_record.checksum,
        action=PublicationAction(audit_record.action),
        authority_level=AuthorityLevel(context_record.authority_level),
        permission_used=PublicationPermission(audit_record.permission_used),
    )


def _replay_existing(
    session: Session,
    *,
    principal: Principal,
    request_hash: str,
    idempotency_key_hash: str,
) -> PublishContextResponse | None:
    existing = get_publication_audit_by_idempotency(
        session,
        principal=principal,
        idempotency_key_hash=idempotency_key_hash,
    )
    if existing is None:
        return None

    if existing.request_hash != request_hash:
        raise PublicationConflictError(
            "idempotency key was reused for a different publication request",
            publication_id=existing.publication_id,
            error_code="idempotency_mismatch",
        )

    if existing.outcome == PublicationOutcome.DENIED.value:
        raise PublicationDeniedError(
            "publication is not authorized",
            publication_id=existing.publication_id,
            error_code=existing.error_code,
        )
    if existing.outcome == PublicationOutcome.CONFLICT.value:
        error_cls = (
            PublicationNotFoundError
            if existing.error_code == "previous_not_found"
            else PublicationConflictError
        )
        raise error_cls(
            "publication could not be applied",
            publication_id=existing.publication_id,
            error_code=existing.error_code,
        )

    if existing.context_record_id is None:
        raise RuntimeError("successful publication audit is missing context record")

    context_record = session.scalar(
        select(ContextItemRecord).where(
            ContextItemRecord.tenant_id == principal.tenant_id,
            ContextItemRecord.id == existing.context_record_id,
        )
    )
    if context_record is None:
        raise RuntimeError("published context record is unavailable")
    return _response_from_audit(
        audit_record=existing,
        context_record=context_record,
    )


def publish_context(
    session: Session,
    *,
    principal: Principal,
    request: PublishContextRequest,
    action: PublicationAction,
    idempotency_key: str,
    previous_id: UUID | None = None,
) -> PublishContextResponse:
    """Authorize, persist, audit, and idempotently replay one publication."""
    bind_session_tenant(session, principal.tenant_id)

    if not idempotency_key.strip() or len(idempotency_key) > 256:
        raise ValueError("idempotency_key must be 1..256 non-whitespace characters")

    if action is PublicationAction.CREATE and previous_id is not None:
        raise ValueError("create publication cannot specify previous_id")
    if action is PublicationAction.SUPERSEDE and previous_id is None:
        raise ValueError("supersede publication requires previous_id")

    item = build_authenticated_context_item(principal=principal, request=request)
    request_hash = publication_request_hash(
        action=action,
        previous_id=previous_id,
        item=item,
    )
    idempotency_key_hash = sha256_text(idempotency_key)
    key_hash = sha256_text(item.key)

    replay = _replay_existing(
        session,
        principal=principal,
        request_hash=request_hash,
        idempotency_key_hash=idempotency_key_hash,
    )
    if replay is not None:
        return replay

    try:
        authorization = authorize_publication(
            principal=principal,
            item=item,
            action=action,
        )
    except PublicationAuthorizationError:
        audit = create_publication_audit(
            session,
            principal=principal,
            action=action,
            authority_level=item.authority_level.value,
            idempotency_key_hash=idempotency_key_hash,
            request_hash=request_hash,
            key_hash=key_hash,
            outcome=PublicationOutcome.DENIED,
            previous_record_id=previous_id,
            error_code="not_authorized",
        )
        session.commit()
        raise PublicationDeniedError(
            "publication is not authorized",
            publication_id=audit.publication_id,
            error_code="not_authorized",
        ) from None

    if action is PublicationAction.SUPERSEDE:
        assert previous_id is not None
        previous = session.scalar(
            select(ContextItemRecord).where(
                ContextItemRecord.tenant_id == principal.tenant_id,
                ContextItemRecord.id == previous_id,
            )
        )
        if previous is None:
            audit = create_publication_audit(
                session,
                principal=principal,
                action=action,
                authority_level=item.authority_level.value,
                idempotency_key_hash=idempotency_key_hash,
                request_hash=request_hash,
                key_hash=key_hash,
                outcome=PublicationOutcome.CONFLICT,
                authorization=authorization,
                previous_record_id=previous_id,
                error_code="previous_not_found",
            )
            session.commit()
            raise PublicationNotFoundError(
                "context item was not found",
                publication_id=audit.publication_id,
                error_code="previous_not_found",
            )

        if previous.authority_level != item.authority_level.value:
            audit = create_publication_audit(
                session,
                principal=principal,
                action=action,
                authority_level=item.authority_level.value,
                idempotency_key_hash=idempotency_key_hash,
                request_hash=request_hash,
                key_hash=key_hash,
                outcome=PublicationOutcome.CONFLICT,
                authorization=authorization,
                previous_record_id=previous_id,
                error_code="authority_transition_requires_approval",
            )
            session.commit()
            raise PublicationConflictError(
                "supersession cannot change authority level",
                publication_id=audit.publication_id,
                error_code="authority_transition_requires_approval",
            )

    try:
        if action is PublicationAction.CREATE:
            record = create_context_item(
                session,
                item,
                publication=authorization,
            )
        else:
            assert previous_id is not None
            record = supersede_context_item(
                session,
                tenant_id=principal.tenant_id,
                previous_id=previous_id,
                replacement=item,
                publication=authorization,
            )
    except ContextItemNotFoundError:
        session.rollback()
        bind_session_tenant(session, principal.tenant_id)
        audit = create_publication_audit(
            session,
            principal=principal,
            action=action,
            authority_level=item.authority_level.value,
            idempotency_key_hash=idempotency_key_hash,
            request_hash=request_hash,
            key_hash=key_hash,
            outcome=PublicationOutcome.CONFLICT,
            authorization=authorization,
            previous_record_id=previous_id,
            error_code="previous_not_found",
        )
        session.commit()
        raise PublicationNotFoundError(
            "context item was not found",
            publication_id=audit.publication_id,
            error_code="previous_not_found",
        ) from None
    except (ContextVersionConflictError, ContextIdentityMismatchError):
        session.rollback()
        bind_session_tenant(session, principal.tenant_id)
        audit = create_publication_audit(
            session,
            principal=principal,
            action=action,
            authority_level=item.authority_level.value,
            idempotency_key_hash=idempotency_key_hash,
            request_hash=request_hash,
            key_hash=key_hash,
            outcome=PublicationOutcome.CONFLICT,
            authorization=authorization,
            previous_record_id=previous_id,
            error_code="version_conflict",
        )
        session.commit()
        raise PublicationConflictError(
            "context publication conflicts with immutable version state",
            publication_id=audit.publication_id,
            error_code="version_conflict",
        ) from None

    audit = create_publication_audit(
        session,
        principal=principal,
        action=action,
        authority_level=item.authority_level.value,
        idempotency_key_hash=idempotency_key_hash,
        request_hash=request_hash,
        key_hash=key_hash,
        outcome=PublicationOutcome.SUCCEEDED,
        authorization=authorization,
        previous_record_id=previous_id,
        context_record_id=record.id,
        logical_id=record.logical_id,
        version=record.version,
    )
    session.commit()

    return _response_from_audit(
        audit_record=audit,
        context_record=record,
    )
