"""Authenticated immutable context publication HTTP surface."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from contextplane.api.dependencies import authenticate_principal, get_database_session
from contextplane.auth import Principal
from contextplane.publishing import PublicationAction
from contextplane.publishing.domain import PublishContextRequest, PublishContextResponse
from contextplane.publishing.runtime import (
    PublicationConflictError,
    PublicationDeniedError,
    PublicationNotFoundError,
    publish_context,
)

router = APIRouter(prefix="/v1/context/items", tags=["context-publishing"])


def _publication_headers(publication_id: UUID | None) -> dict[str, str] | None:
    if publication_id is None:
        return None
    return {"X-ContextPlane-Publication-ID": str(publication_id)}


def _publish(
    *,
    request: PublishContextRequest,
    principal: Principal,
    session: Session,
    idempotency_key: str,
    action: PublicationAction,
    previous_id: UUID | None = None,
) -> PublishContextResponse:
    try:
        return publish_context(
            session,
            principal=principal,
            request=request,
            action=action,
            idempotency_key=idempotency_key,
            previous_id=previous_id,
        )
    except PublicationDeniedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="publication is not authorized",
            headers=_publication_headers(exc.publication_id),
        ) from None
    except PublicationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="context item was not found",
            headers=_publication_headers(exc.publication_id),
        ) from None
    except PublicationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="context publication conflict",
            headers=_publication_headers(exc.publication_id),
        ) from None


@router.post("", response_model=PublishContextResponse, status_code=status.HTTP_201_CREATED)
def create_context(
    request: PublishContextRequest,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=256),
    ],
) -> PublishContextResponse:
    """Create the first immutable context version for the authenticated tenant."""
    return _publish(
        request=request,
        principal=principal,
        session=session,
        idempotency_key=idempotency_key,
        action=PublicationAction.CREATE,
    )


@router.post(
    "/{previous_id}/supersede",
    response_model=PublishContextResponse,
    status_code=status.HTTP_201_CREATED,
)
def supersede_context(
    previous_id: UUID,
    request: PublishContextRequest,
    principal: Annotated[Principal, Depends(authenticate_principal)],
    session: Annotated[Session, Depends(get_database_session)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=256),
    ],
) -> PublishContextResponse:
    """Create the next immutable version of one authorized context item."""
    return _publish(
        request=request,
        principal=principal,
        session=session,
        idempotency_key=idempotency_key,
        action=PublicationAction.SUPERSEDE,
        previous_id=previous_id,
    )
