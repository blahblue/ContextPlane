"""MCP v2 adapter over the protocol-independent ContextPlane runtime service."""

from collections.abc import Callable
from typing import Any

from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import AnyHttpUrl
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from contextplane.auth import (
    AuthenticationError,
    EntraValidatorConfig,
    Principal,
    StaticKeyEntraValidator,
)
from contextplane.cache import InMemoryResolutionCache
from contextplane.context_registry.domain import ContextDomain
from contextplane.database import build_engine
from contextplane.policy import PolicyRule
from contextplane.runtime import (
    ResolveContextRequest,
    ResolveContextResponse,
    RuntimeGovernanceConflictError,
    RuntimePolicyConfigurationError,
    resolve_context_runtime,
)
from contextplane.settings import Settings

PrincipalProvider = Callable[[], Principal]
PolicyRulesProvider = Callable[[], tuple[PolicyRule, ...]]


class ContextPlaneEntraTokenVerifier(TokenVerifier):
    """Adapt ContextPlane's Entra validator to the MCP OAuth resource-server boundary."""

    def __init__(self, validator: StaticKeyEntraValidator) -> None:
        self._validator = validator

    async def verify_token(self, token: str) -> AccessToken | None:
        """Return normalized ContextPlane identity in verified access-token claims."""
        try:
            principal = self._validator.validate(token)
        except AuthenticationError:
            return None

        if principal.client_id is None:
            return None

        permissions = principal.scopes | principal.roles
        if "context.resolve" not in permissions:
            return None

        return AccessToken(
            token=token,
            client_id=principal.client_id,
            scopes=sorted(permissions),
            subject=principal.subject,
            claims={
                "contextplane_principal": principal.model_dump(mode="json"),
            },
        )


def _authenticated_principal() -> Principal:
    """Read the principal deposited by the MCP HTTP auth middleware."""
    token = get_access_token()
    if token is None or token.claims is None:
        raise ToolError("authentication required")

    raw = token.claims.get("contextplane_principal")
    if not isinstance(raw, dict):
        raise ToolError("authenticated principal is unavailable")

    try:
        return Principal.model_validate(raw)
    except (TypeError, ValueError):
        raise ToolError("authenticated principal is invalid") from None


def build_mcp_server(
    *,
    engine: Engine,
    cache: InMemoryResolutionCache,
    rules_provider: PolicyRulesProvider,
    principal_provider: PrincipalProvider | None = None,
    token_verifier: TokenVerifier | None = None,
    auth: AuthSettings | None = None,
) -> MCPServer:
    """Build an MCP server whose tool delegates to the shared runtime service.

    principal_provider is a test/embedding seam. Production Streamable HTTP
    deployments should omit it and supply token_verifier + auth.
    """
    if principal_provider is None and (token_verifier is None or auth is None):
        raise ValueError(
            "production MCP server requires token_verifier and auth when "
            "principal_provider is not supplied"
        )

    if principal_provider is not None and (token_verifier is not None or auth is not None):
        raise ValueError(
            "principal_provider cannot be combined with MCP HTTP auth configuration"
        )

    kwargs: dict[str, Any] = {}
    if token_verifier is not None and auth is not None:
        kwargs = {
            "token_verifier": token_verifier,
            "auth": auth,
        }

    server = MCPServer("ContextPlane", **kwargs)
    resolve_principal = principal_provider or _authenticated_principal

    @server.tool(
        name="resolve_context",
        description=(
            "Resolve the governed organizational context that applies to the "
            "authenticated caller and requested task. Identity is supplied by "
            "the MCP authentication boundary, not by tool arguments."
        ),
        structured_output=True,
    )
    def resolve_context(
        domains: list[ContextDomain],
        keys: list[str] | None = None,
        task: str | None = None,
        audience: str | None = None,
        environment: str | None = None,
    ) -> ResolveContextResponse:
        """Resolve organizational context through the shared ContextPlane runtime."""
        try:
            request = ResolveContextRequest(
                domains=frozenset(domains),
                keys=None if keys is None else frozenset(keys),
                task=task,
                audience=audience,
                environment=environment,
            )
        except ValueError:
            raise ToolError("invalid context request") from None

        principal = resolve_principal()

        try:
            with Session(engine) as session:
                return resolve_context_runtime(
                    request=request,
                    principal=principal,
                    session=session,
                    rules=rules_provider(),
                    cache=cache,
                )
        except RuntimePolicyConfigurationError as exc:
            raise ToolError(
                f"policy configuration is invalid; resolution_id={exc.resolution_id}"
            ) from None
        except RuntimeGovernanceConflictError as exc:
            raise ToolError(
                f"context governance conflict; resolution_id={exc.resolution_id}"
            ) from None

    return server


def build_mcp_server_from_settings(
    settings: Settings | None = None,
    *,
    rules_provider: PolicyRulesProvider = tuple,
) -> MCPServer:
    """Build the reference authenticated Streamable HTTP MCP server."""
    resolved = settings or Settings()

    required = (
        resolved.entra_tenant_id,
        resolved.entra_issuer,
        resolved.entra_audience,
        resolved.entra_public_key_pem,
        resolved.mcp_resource_server_url,
    )
    if any(value is None for value in required):
        raise RuntimeError(
            "MCP server requires Entra tenant/issuer/audience/public key and "
            "mcp_resource_server_url configuration"
        )

    tenant_id, issuer, audience, public_key, resource_url = required
    assert tenant_id is not None
    assert issuer is not None
    assert audience is not None
    assert public_key is not None
    assert resource_url is not None

    validator = StaticKeyEntraValidator(
        EntraValidatorConfig(
            tenant_id=tenant_id,
            issuer=issuer,
            audience=audience,
            public_key_pem=public_key.replace("\\n", "\n"),
        )
    )
    token_verifier = ContextPlaneEntraTokenVerifier(validator)

    return build_mcp_server(
        engine=build_engine(resolved),
        cache=InMemoryResolutionCache(
            ttl_seconds=resolved.resolution_cache_ttl_seconds,
            max_entries=resolved.resolution_cache_max_entries,
        ),
        rules_provider=rules_provider,
        token_verifier=token_verifier,
        auth=AuthSettings(
            issuer_url=AnyHttpUrl(issuer),
            resource_server_url=AnyHttpUrl(resource_url),
            required_scopes=["context.resolve"],
            validate_token_resource=False,
        ),
    )


def main() -> None:
    """Run the reference remote MCP server over Streamable HTTP."""
    server = build_mcp_server_from_settings()
    server.run(
        transport="streamable-http",
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    main()
