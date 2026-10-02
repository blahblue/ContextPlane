"""High-authority draft, approval, and activation workflow."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contextplane.auth import Principal, PrincipalKind
from contextplane.context_registry.db import ContextItemRecord
from contextplane.context_registry.domain import AuthorityLevel, ContextItemCreate
from contextplane.context_registry.repository import (
    ContextIdentityMismatchError,
    ContextItemNotFoundError,
    ContextVersionConflictError,
    create_context_item,
    supersede_context_item,
)
from contextplane.persistence.tenant import bind_session_tenant
from contextplane.publishing.approval_db import PublicationProposalRecord
from contextplane.publishing.approval_repository import (
    create_approval_event,
    get_proposal,
    get_proposal_by_actor_idempotency,
    get_successful_event,
)
from contextplane.publishing.build import (
    build_authenticated_context_item,
    publication_request_hash,
    sha256_text,
)
from contextplane.publishing.domain import (
    ApprovalEventOutcome,
    ApprovalEventType,
    CreatePublicationProposalRequest,
    PublicationAction,
    PublicationApprovalPermission,
    PublicationAuthorization,
    PublicationOutcome,
    PublicationPermission,
    PublicationProposalResponse,
    PublicationProposalState,
)
from contextplane.publishing.repository import create_publication_audit
from contextplane.publishing.service import (
    PublicationAuthorizationError,
    authorize_activation,
    authorize_approval,
    authorize_publication,
)


class ApprovalWorkflowError(RuntimeError):
    """Base safe workflow error carrying a correlation identifier."""

    def __init__(
        self,
        message: str,
        *,
        proposal_id: UUID | None = None,
        publication_id: UUID | None = None,
        event_id: UUID | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.proposal_id = proposal_id
        self.publication_id = publication_id
        self.event_id = event_id
        self.error_code = error_code


class ApprovalWorkflowDeniedError(ApprovalWorkflowError):
    """Caller lacks publication/approval/activation permission."""


class ApprovalWorkflowConflictError(ApprovalWorkflowError):
    """Workflow state or immutable version state conflicts with the request."""


class ApprovalWorkflowNotFoundError(ApprovalWorkflowError):
    """Proposal or predecessor is not visible in the authenticated tenant."""


def _validate_idempotency_key(value: str) -> None:
    if not value.strip() or len(value) > 256:
        raise ValueError(
            "idempotency_key must be 1..256 non-whitespace characters"
        )


def _proposal_response(
    session: Session,
    *,
    proposal: PublicationProposalRecord,
) -> PublicationProposalResponse:
    approval = get_successful_event(
        session,
        tenant_id=proposal.tenant_id,
        proposal_id=proposal.proposal_id,
        event_type=ApprovalEventType.APPROVE,
    )
    activation = get_successful_event(
        session,
        tenant_id=proposal.tenant_id,
        proposal_id=proposal.proposal_id,
        event_type=ApprovalEventType.ACTIVATE,
    )

    if activation is not None:
        state = PublicationProposalState.ACTIVE
    elif approval is not None:
        state = PublicationProposalState.APPROVED
    else:
        state = PublicationProposalState.DRAFT

    return PublicationProposalResponse(
        proposal_id=proposal.proposal_id,
        state=state,
        action=PublicationAction(proposal.action),
        authority_level=AuthorityLevel(proposal.authority_level),
        previous_id=proposal.previous_record_id,
        approval_event_id=approval.event_id if approval is not None else None,
        activation_event_id=(
            activation.event_id if activation is not None else None
        ),
        context_record_id=(
            activation.context_record_id if activation is not None else None
        ),
        logical_id=activation.logical_id if activation is not None else None,
        version=activation.version if activation is not None else None,
    )


def _publisher_authorization(
    proposal: PublicationProposalRecord,
) -> PublicationAuthorization:
    return PublicationAuthorization(
        tenant_id=proposal.tenant_id,
        subject=proposal.publisher_subject,
        principal_kind=PrincipalKind(proposal.publisher_kind),
        client_id=proposal.publisher_client_id,
        action=PublicationAction(proposal.action),
        authority_level=AuthorityLevel(proposal.authority_level),
        permission_used=PublicationPermission(proposal.publication_permission),
    )


def _audit_proposal_creation_failure(
    session: Session,
    *,
    principal: Principal,
    request: CreatePublicationProposalRequest,
    item: ContextItemCreate,
    idempotency_key: str,
    authorization: PublicationAuthorization | None,
    outcome: PublicationOutcome,
    error_code: str,
) -> UUID:
    audit = create_publication_audit(
        session,
        principal=principal,
        action=request.action,
        authority_level=item.authority_level.value,
        idempotency_key_hash=sha256_text(
            f"proposal:{idempotency_key}"
        ),
        request_hash=publication_request_hash(
            action=request.action,
            previous_id=request.previous_id,
            item=item,
        ),
        key_hash=sha256_text(item.key),
        outcome=outcome,
        authorization=authorization,
        previous_record_id=request.previous_id,
        error_code=error_code,
    )
    session.commit()
    return audit.publication_id


def create_publication_proposal(
    session: Session,
    *,
    principal: Principal,
    request: CreatePublicationProposalRequest,
    idempotency_key: str,
) -> PublicationProposalResponse:
    """Create or replay an immutable policy/mandatory-control draft."""
    bind_session_tenant(session, principal.tenant_id)
    _validate_idempotency_key(idempotency_key)

    item = build_authenticated_context_item(
        principal=principal,
        request=request.context,
    )
    request_hash = publication_request_hash(
        action=request.action,
        previous_id=request.previous_id,
        item=item,
    )
    idempotency_hash = sha256_text(idempotency_key)

    existing = get_proposal_by_actor_idempotency(
        session,
        principal=principal,
        idempotency_key_hash=idempotency_hash,
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ApprovalWorkflowConflictError(
                "idempotency key was reused for a different proposal",
                proposal_id=existing.proposal_id,
                error_code="idempotency_mismatch",
            )
        return _proposal_response(session, proposal=existing)

    try:
        authorization = authorize_publication(
            principal=principal,
            item=item,
            action=request.action,
        )
    except PublicationAuthorizationError:
        publication_id = _audit_proposal_creation_failure(
            session,
            principal=principal,
            request=request,
            item=item,
            idempotency_key=idempotency_key,
            authorization=None,
            outcome=PublicationOutcome.DENIED,
            error_code="not_authorized",
        )
        raise ApprovalWorkflowDeniedError(
            "publication proposal is not authorized",
            publication_id=publication_id,
            error_code="not_authorized",
        ) from None

    if request.action is PublicationAction.SUPERSEDE:
        assert request.previous_id is not None
        previous = session.scalar(
            select(ContextItemRecord).where(
                ContextItemRecord.tenant_id == principal.tenant_id,
                ContextItemRecord.id == request.previous_id,
            )
        )
        if previous is None:
            publication_id = _audit_proposal_creation_failure(
                session,
                principal=principal,
                request=request,
                item=item,
                idempotency_key=idempotency_key,
                authorization=authorization,
                outcome=PublicationOutcome.CONFLICT,
                error_code="previous_not_found",
            )
            raise ApprovalWorkflowNotFoundError(
                "context item was not found",
                publication_id=publication_id,
                error_code="previous_not_found",
            )
        if item.key != previous.key or item.domain.value != previous.domain:
            publication_id = _audit_proposal_creation_failure(
                session,
                principal=principal,
                request=request,
                item=item,
                idempotency_key=idempotency_key,
                authorization=authorization,
                outcome=PublicationOutcome.CONFLICT,
                error_code="identity_mismatch",
            )
            raise ApprovalWorkflowConflictError(
                "proposal must preserve logical key and domain",
                publication_id=publication_id,
                error_code="identity_mismatch",
            )

    proposal = PublicationProposalRecord(
        tenant_id=principal.tenant_id,
        publisher_kind=principal.kind.value,
        publisher_subject=principal.subject,
        publisher_client_id=principal.client_id,
        action=request.action.value,
        authority_level=item.authority_level.value,
        publication_permission=authorization.permission_used.value,
        previous_record_id=request.previous_id,
        item_payload=item.model_dump(mode="json"),
        idempotency_key_hash=idempotency_hash,
        request_hash=request_hash,
    )
    session.add(proposal)
    try:
        session.commit()
        bind_session_tenant(session, principal.tenant_id)
    except IntegrityError:
        session.rollback()
        bind_session_tenant(session, principal.tenant_id)
        existing = get_proposal_by_actor_idempotency(
            session,
            principal=principal,
            idempotency_key_hash=idempotency_hash,
        )
        if existing is None or existing.request_hash != request_hash:
            raise ApprovalWorkflowConflictError(
                "publication proposal conflicts with an existing request",
                error_code="proposal_conflict",
            ) from None
        return _proposal_response(session, proposal=existing)

    return _proposal_response(session, proposal=proposal)


def approve_publication_proposal(
    session: Session,
    *,
    principal: Principal,
    proposal_id: UUID,
    require_distinct_approver: bool,
) -> PublicationProposalResponse:
    """Approve one draft while preserving immutable approval provenance."""
    bind_session_tenant(session, principal.tenant_id)
    proposal = get_proposal(
        session,
        tenant_id=principal.tenant_id,
        proposal_id=proposal_id,
        for_update=True,
    )
    if proposal is None:
        raise ApprovalWorkflowNotFoundError(
            "publication proposal was not found",
            proposal_id=proposal_id,
            error_code="proposal_not_found",
        )

    authority = AuthorityLevel(proposal.authority_level)
    try:
        permission = authorize_approval(
            principal=principal,
            authority_level=authority,
            publisher_kind=PrincipalKind(proposal.publisher_kind),
            publisher_subject=proposal.publisher_subject,
            require_distinct_approver=require_distinct_approver,
        )
    except PublicationAuthorizationError as exc:
        event = create_approval_event(
            session,
            principal=principal,
            proposal_id=proposal.proposal_id,
            event_type=ApprovalEventType.APPROVE,
            outcome=ApprovalEventOutcome.DENIED,
            error_code="approval_not_authorized",
        )
        session.commit()
        raise ApprovalWorkflowDeniedError(
            str(exc),
            proposal_id=proposal.proposal_id,
            event_id=event.event_id,
            error_code="approval_not_authorized",
        ) from None

    existing = get_successful_event(
        session,
        tenant_id=principal.tenant_id,
        proposal_id=proposal.proposal_id,
        event_type=ApprovalEventType.APPROVE,
    )
    if existing is None:
        create_approval_event(
            session,
            principal=principal,
            proposal_id=proposal.proposal_id,
            event_type=ApprovalEventType.APPROVE,
            outcome=ApprovalEventOutcome.SUCCEEDED,
            permission_used=permission,
        )
        session.commit()
        bind_session_tenant(session, principal.tenant_id)

    return _proposal_response(session, proposal=proposal)


def activate_publication_proposal(
    session: Session,
    *,
    principal: Principal,
    proposal_id: UUID,
) -> PublicationProposalResponse:
    """Activate an approved high-authority proposal as an immutable context version."""
    bind_session_tenant(session, principal.tenant_id)
    proposal = get_proposal(
        session,
        tenant_id=principal.tenant_id,
        proposal_id=proposal_id,
        for_update=True,
    )
    if proposal is None:
        raise ApprovalWorkflowNotFoundError(
            "publication proposal was not found",
            proposal_id=proposal_id,
            error_code="proposal_not_found",
        )

    authority = AuthorityLevel(proposal.authority_level)
    try:
        permission = authorize_activation(
            principal=principal,
            authority_level=authority,
        )
    except PublicationAuthorizationError as exc:
        event = create_approval_event(
            session,
            principal=principal,
            proposal_id=proposal.proposal_id,
            event_type=ApprovalEventType.ACTIVATE,
            outcome=ApprovalEventOutcome.DENIED,
            error_code="activation_not_authorized",
        )
        session.commit()
        raise ApprovalWorkflowDeniedError(
            str(exc),
            proposal_id=proposal.proposal_id,
            event_id=event.event_id,
            error_code="activation_not_authorized",
        ) from None

    existing_activation = get_successful_event(
        session,
        tenant_id=principal.tenant_id,
        proposal_id=proposal.proposal_id,
        event_type=ApprovalEventType.ACTIVATE,
    )
    if existing_activation is not None:
        return _proposal_response(session, proposal=proposal)

    approval = get_successful_event(
        session,
        tenant_id=principal.tenant_id,
        proposal_id=proposal.proposal_id,
        event_type=ApprovalEventType.APPROVE,
    )
    if approval is None:
        event = create_approval_event(
            session,
            principal=principal,
            proposal_id=proposal.proposal_id,
            event_type=ApprovalEventType.ACTIVATE,
            outcome=ApprovalEventOutcome.CONFLICT,
            permission_used=permission,
            error_code="approval_required",
        )
        session.commit()
        raise ApprovalWorkflowConflictError(
            "publication proposal must be approved before activation",
            proposal_id=proposal.proposal_id,
            event_id=event.event_id,
            error_code="approval_required",
        )

    item = ContextItemCreate.model_validate(proposal.item_payload)
    publisher_authorization = _publisher_authorization(proposal)

    try:
        if PublicationAction(proposal.action) is PublicationAction.CREATE:
            record = create_context_item(
                session,
                item,
                publication=publisher_authorization,
            )
        else:
            assert proposal.previous_record_id is not None
            record = supersede_context_item(
                session,
                tenant_id=proposal.tenant_id,
                previous_id=proposal.previous_record_id,
                replacement=item,
                publication=publisher_authorization,
            )
    except ContextItemNotFoundError:
        session.rollback()
        bind_session_tenant(session, principal.tenant_id)
        event = create_approval_event(
            session,
            principal=principal,
            proposal_id=proposal_id,
            event_type=ApprovalEventType.ACTIVATE,
            outcome=ApprovalEventOutcome.CONFLICT,
            permission_used=permission,
            error_code="previous_not_found",
        )
        session.commit()
        raise ApprovalWorkflowNotFoundError(
            "supersession target is no longer available",
            proposal_id=proposal_id,
            event_id=event.event_id,
            error_code="previous_not_found",
        ) from None
    except (ContextVersionConflictError, ContextIdentityMismatchError):
        session.rollback()
        bind_session_tenant(session, principal.tenant_id)
        event = create_approval_event(
            session,
            principal=principal,
            proposal_id=proposal_id,
            event_type=ApprovalEventType.ACTIVATE,
            outcome=ApprovalEventOutcome.CONFLICT,
            permission_used=permission,
            error_code="version_conflict",
        )
        session.commit()
        raise ApprovalWorkflowConflictError(
            "proposal activation conflicts with immutable version state",
            proposal_id=proposal_id,
            event_id=event.event_id,
            error_code="version_conflict",
        ) from None

    create_approval_event(
        session,
        principal=principal,
        proposal_id=proposal.proposal_id,
        event_type=ApprovalEventType.ACTIVATE,
        outcome=ApprovalEventOutcome.SUCCEEDED,
        permission_used=permission,
        context_record_id=record.id,
        logical_id=record.logical_id,
        version=record.version,
    )
    session.commit()
    bind_session_tenant(session, principal.tenant_id)

    return _proposal_response(session, proposal=proposal)
