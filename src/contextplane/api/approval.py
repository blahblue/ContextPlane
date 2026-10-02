"""Authenticated high-authority proposal, approval, and activation API."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from contextplane.api.dependencies import (
    authenticate_principal,
    get_database_session,
    get_settings,
)
from contextplane.auth import Principal
from contextplane.publishing.approval_runtime import (
    ApprovalWorkflowConflictError,
    ApprovalWorkflowDeniedError,
    ApprovalWorkflowNotFoundError,
    activate_publication_proposal,
    approve_publication_proposal,
    create_publication_proposal,
)
from contextplane.publishing.domain import (
    CreatePublicationProposalRequest,
    PublicationProposalResponse,
)
from contextplane.settings import Settings

router = APIRouter(
    prefix="/v1/context/publication-proposals",
    tags=["context-publishing"],
)


def _workflow_headers(exc: Exception) -> dict[str, str] | None:
    headers: dict[str, str] = {}
    proposal_id = getattr(exc, "proposal_id", None)
    publication_id = getattr(exc, "publication_id", None)
    event_id = getattr(exc, "event_id", None)
    if proposal_id is not None:
        headers["X-ContextPlane-Proposal-ID"] = str(proposal_id)
    if publication_id is not None:
        headers["X-ContextPlane-Publication-ID"] = str(publication_id)
    if event_id is not None:
        headers["X-ContextPlane-Approval-Event-ID"] = str(event_id)
    return headers or None


def _raise_workflow_error(exc: Exception) -> None:
    if isinstance(exc, ApprovalWorkflowDeniedError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="publication workflow action is not authorized",
            headers=_workflow_headers(exc),
        ) from None
    if isinstance(exc, ApprovalWorkflowNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="publication workflow resource was not found",
            headers=_workflow_headers(exc),
        ) from None
    if isinstance(exc, ApprovalWorkflowConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="publication workflow conflict",
            headers=_workflow_headers(exc),
        ) from None
    raise exc


@router.post(
    "",
    response_model=PublicationProposalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_proposal(
    request: CreatePublicationProposalRequest,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=256),
    ],
) -> PublicationProposalResponse:
    """Create an immutable high-authority draft."""
    try:
        return create_publication_proposal(
            session,
            principal=principal,
            request=request,
            idempotency_key=idempotency_key,
        )
    except (
        ApprovalWorkflowDeniedError,
        ApprovalWorkflowNotFoundError,
        ApprovalWorkflowConflictError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{proposal_id}/approve",
    response_model=PublicationProposalResponse,
)
def approve_proposal(
    proposal_id: UUID,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PublicationProposalResponse:
    """Approve a high-authority draft under configured separation of duties."""
    try:
        return approve_publication_proposal(
            session,
            principal=principal,
            proposal_id=proposal_id,
            require_distinct_approver=(
                settings.publishing_require_distinct_approver
            ),
        )
    except (
        ApprovalWorkflowDeniedError,
        ApprovalWorkflowNotFoundError,
        ApprovalWorkflowConflictError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")


@router.post(
    "/{proposal_id}/activate",
    response_model=PublicationProposalResponse,
)
def activate_proposal(
    proposal_id: UUID,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
) -> PublicationProposalResponse:
    """Activate an approved draft as an immutable context version."""
    try:
        return activate_publication_proposal(
            session,
            principal=principal,
            proposal_id=proposal_id,
        )
    except (
        ApprovalWorkflowDeniedError,
        ApprovalWorkflowNotFoundError,
        ApprovalWorkflowConflictError,
    ) as exc:
        _raise_workflow_error(exc)
        raise AssertionError("unreachable")
