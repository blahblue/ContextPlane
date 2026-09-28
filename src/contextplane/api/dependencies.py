"""FastAPI dependencies for authenticated runtime resolution."""

from collections.abc import Iterator
from typing import Annotated
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from contextplane.auth import (
    AuthenticationError,
    EntraValidatorConfig,
    Principal,
    PrincipalValidator,
    StaticKeyEntraValidator,
)
from contextplane.database import build_engine
from contextplane.policy import PolicyRule
from contextplane.settings import Settings

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_settings() -> Settings:
    """Return process-level runtime settings."""
    return Settings()


@lru_cache
def get_engine() -> Engine:
    """Create the process-level SQLAlchemy engine lazily."""
    return build_engine(get_settings())


def get_database_session() -> Iterator[Session]:
    """Yield one database session per request."""
    with Session(get_engine()) as session:
        yield session


def build_principal_validator(settings: Settings) -> PrincipalValidator:
    """Build the configured reference Entra validator or fail unavailable."""
    required = (
        settings.entra_tenant_id,
        settings.entra_issuer,
        settings.entra_audience,
        settings.entra_public_key_pem,
    )
    if any(value is None for value in required):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="authentication provider is not configured",
        )

    tenant_id, issuer, audience, public_key = required
    assert tenant_id is not None
    assert issuer is not None
    assert audience is not None
    assert public_key is not None

    return StaticKeyEntraValidator(
        EntraValidatorConfig(
            tenant_id=tenant_id,
            issuer=issuer,
            audience=audience,
            public_key_pem=public_key.replace("\\n", "\n"),
        )
    )


def authenticate_principal(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Principal:
    """Validate one bearer token and return the normalized principal."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="bearer authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    validator = build_principal_validator(settings)

    try:
        return validator.validate(credentials.credentials)
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication failed",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


def get_policy_rules() -> tuple[PolicyRule, ...]:
    """Return configured runtime policy rules.

    Policy persistence is intentionally deferred; tests and embedding applications
    can override this dependency.
    """
    return ()
