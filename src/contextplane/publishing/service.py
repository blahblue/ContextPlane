"""Fail-closed authorization rules for context publishing."""

from contextplane.auth import Principal, PrincipalKind, principal_has_permission
from contextplane.context_registry.domain import AuthorityLevel, ContextItemCreate
from contextplane.publishing.domain import (
    PublicationAction,
    PublicationAuthorization,
    PublicationPermission,
)


class PublicationAuthorizationError(PermissionError):
    """Raised when an authenticated principal may not publish the requested context."""


_AUTHORITY_PERMISSION = {
    AuthorityLevel.PREFERENCE: PublicationPermission.PREFERENCE,
    AuthorityLevel.RECOMMENDATION: PublicationPermission.RECOMMENDATION,
    AuthorityLevel.STANDARD: PublicationPermission.STANDARD,
    AuthorityLevel.POLICY: PublicationPermission.POLICY,
    AuthorityLevel.MANDATORY_CONTROL: PublicationPermission.MANDATORY_CONTROL,
}


def _has(principal: Principal, permission: PublicationPermission) -> bool:
    return principal_has_permission(principal, permission.value)


def authorize_publication(
    *,
    principal: Principal,
    item: ContextItemCreate,
    action: PublicationAction,
) -> PublicationAuthorization:
    """Authorize one create/supersede operation against immutable principal identity."""
    if item.scope.tenant_id != principal.tenant_id:
        raise PublicationAuthorizationError("publication is not authorized")

    if item.authority_level is AuthorityLevel.PREFERENCE:
        is_self_user_preference = (
            principal.kind is PrincipalKind.USER
            and item.scope.user_id == principal.subject
            and item.scope.agent_id is None
        )
        if is_self_user_preference and _has(
            principal,
            PublicationPermission.PREFERENCE_SELF,
        ):
            permission = PublicationPermission.PREFERENCE_SELF
        elif _has(principal, PublicationPermission.PREFERENCE):
            permission = PublicationPermission.PREFERENCE
        else:
            raise PublicationAuthorizationError("publication is not authorized")
    else:
        permission = _AUTHORITY_PERMISSION[item.authority_level]
        if not _has(principal, permission):
            raise PublicationAuthorizationError("publication is not authorized")

    return PublicationAuthorization(
        tenant_id=principal.tenant_id,
        subject=principal.subject,
        principal_kind=principal.kind,
        client_id=principal.client_id,
        action=action,
        authority_level=item.authority_level,
        permission_used=permission,
    )
