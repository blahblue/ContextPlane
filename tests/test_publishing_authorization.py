from datetime import UTC, datetime

import pytest

from contextplane.auth import Principal, PrincipalKind
from contextplane.context_registry import (
    AuthorityLevel,
    ContextDomain,
    ContextItemCreate,
    ContextScope,
    ContextSource,
    OverridePolicy,
    SensitivityLevel,
    SourceType,
)
from contextplane.publishing import (
    PublicationAction,
    PublicationAuthorizationError,
    PublicationPermission,
    authorize_publication,
)


def principal(
    *,
    tenant: str = "acme",
    subject: str = "user-a",
    kind: PrincipalKind = PrincipalKind.USER,
    client_id: str | None = "client-a",
    permissions: frozenset[str] = frozenset(),
) -> Principal:
    return Principal(
        tenant_id=tenant,
        subject=subject,
        kind=kind,
        client_id=client_id,
        scopes=permissions,
    )


def item(
    *,
    tenant: str = "acme",
    authority: AuthorityLevel,
    user_id: str | None = None,
    agent_id: str | None = None,
) -> ContextItemCreate:
    return ContextItemCreate(
        key="engineering.example",
        value={"value": "example"},
        domain=ContextDomain.ENGINEERING,
        scope=ContextScope(
            tenant_id=tenant,
            user_id=user_id,
            agent_id=agent_id,
        ),
        owner="engineering",
        source=ContextSource(
            type=SourceType.API,
            identifier="publishing-test",
        ),
        authority_level=authority,
        effective_from=datetime(2026, 10, 2, tzinfo=UTC),
        sensitivity=SensitivityLevel.INTERNAL,
        override_policy=OverridePolicy.DENY,
        checksum="a" * 64,
    )


@pytest.mark.parametrize(
    ("authority", "permission"),
    [
        (
            AuthorityLevel.PREFERENCE,
            PublicationPermission.PREFERENCE,
        ),
        (
            AuthorityLevel.RECOMMENDATION,
            PublicationPermission.RECOMMENDATION,
        ),
        (
            AuthorityLevel.STANDARD,
            PublicationPermission.STANDARD,
        ),
        (
            AuthorityLevel.POLICY,
            PublicationPermission.POLICY,
        ),
        (
            AuthorityLevel.MANDATORY_CONTROL,
            PublicationPermission.MANDATORY_CONTROL,
        ),
    ],
)
def test_each_authority_requires_its_explicit_permission(
    authority: AuthorityLevel,
    permission: PublicationPermission,
) -> None:
    decision = authorize_publication(
        principal=principal(permissions=frozenset({permission.value})),
        item=item(authority=authority),
        action=PublicationAction.CREATE,
    )

    assert decision.authority_level is authority
    assert decision.permission_used is permission
    assert decision.tenant_id == "acme"
    assert decision.subject == "user-a"


@pytest.mark.parametrize(
    "authority",
    [
        AuthorityLevel.RECOMMENDATION,
        AuthorityLevel.STANDARD,
        AuthorityLevel.POLICY,
        AuthorityLevel.MANDATORY_CONTROL,
    ],
)
def test_lower_or_unrelated_permission_does_not_imply_higher_authority(
    authority: AuthorityLevel,
) -> None:
    with pytest.raises(
        PublicationAuthorizationError,
        match="publication is not authorized",
    ):
        authorize_publication(
            principal=principal(
                permissions=frozenset(
                    {
                        PublicationPermission.PREFERENCE.value,
                        PublicationPermission.PREFERENCE_SELF.value,
                    }
                )
            ),
            item=item(authority=authority),
            action=PublicationAction.CREATE,
        )


def test_mandatory_control_permission_does_not_implicitly_grant_other_authorities() -> None:
    with pytest.raises(PublicationAuthorizationError):
        authorize_publication(
            principal=principal(
                permissions=frozenset(
                    {PublicationPermission.MANDATORY_CONTROL.value}
                )
            ),
            item=item(authority=AuthorityLevel.STANDARD),
            action=PublicationAction.CREATE,
        )


def test_user_can_publish_own_preference_with_self_permission() -> None:
    decision = authorize_publication(
        principal=principal(
            subject="user-a",
            permissions=frozenset(
                {PublicationPermission.PREFERENCE_SELF.value}
            ),
        ),
        item=item(
            authority=AuthorityLevel.PREFERENCE,
            user_id="user-a",
        ),
        action=PublicationAction.SUPERSEDE,
    )

    assert decision.permission_used is PublicationPermission.PREFERENCE_SELF
    assert decision.action is PublicationAction.SUPERSEDE


def test_self_preference_permission_cannot_target_another_user() -> None:
    with pytest.raises(PublicationAuthorizationError):
        authorize_publication(
            principal=principal(
                subject="user-a",
                permissions=frozenset(
                    {PublicationPermission.PREFERENCE_SELF.value}
                ),
            ),
            item=item(
                authority=AuthorityLevel.PREFERENCE,
                user_id="user-b",
            ),
            action=PublicationAction.CREATE,
        )


def test_self_preference_permission_cannot_publish_unscoped_preference() -> None:
    with pytest.raises(PublicationAuthorizationError):
        authorize_publication(
            principal=principal(
                permissions=frozenset(
                    {PublicationPermission.PREFERENCE_SELF.value}
                ),
            ),
            item=item(authority=AuthorityLevel.PREFERENCE),
            action=PublicationAction.CREATE,
        )


def test_agent_cannot_use_user_self_preference_permission() -> None:
    with pytest.raises(PublicationAuthorizationError):
        authorize_publication(
            principal=principal(
                kind=PrincipalKind.AGENT,
                subject="agent-a",
                client_id="agent-client",
                permissions=frozenset(
                    {PublicationPermission.PREFERENCE_SELF.value}
                ),
            ),
            item=item(
                authority=AuthorityLevel.PREFERENCE,
                user_id="agent-a",
            ),
            action=PublicationAction.CREATE,
        )


def test_cross_tenant_publication_fails_even_with_high_authority_permission() -> None:
    with pytest.raises(PublicationAuthorizationError):
        authorize_publication(
            principal=principal(
                tenant="tenant-a",
                permissions=frozenset(
                    {PublicationPermission.MANDATORY_CONTROL.value}
                ),
            ),
            item=item(
                tenant="tenant-b",
                authority=AuthorityLevel.MANDATORY_CONTROL,
            ),
            action=PublicationAction.CREATE,
        )


def test_roles_can_grant_publication_permission() -> None:
    actor = Principal(
        tenant_id="acme",
        subject="security-publisher",
        kind=PrincipalKind.USER,
        client_id="client-a",
        roles=frozenset({PublicationPermission.POLICY.value}),
    )

    decision = authorize_publication(
        principal=actor,
        item=item(authority=AuthorityLevel.POLICY),
        action=PublicationAction.CREATE,
    )

    assert decision.permission_used is PublicationPermission.POLICY
