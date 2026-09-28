# ADR-010 — Map Microsoft Entra Access Tokens to Immutable ContextPlane Identity

**Status:** Accepted for MVP  
**Date:** 2026-09-28

## Context

ContextPlane uses a provider-neutral `Principal`, while Microsoft Entra access tokens use provider-specific claims.

For authorization, Microsoft recommends stable tenant/object identifiers rather than mutable display claims such as email, UPN, or preferred username. Entra also distinguishes delegated user permissions (`scp`) from application permissions (`roles`), and Microsoft Entra Agent ID adds agent-specific function claims.

Group membership has an important edge case: when a JWT exceeds the group limit, Entra omits the complete `groups` array and emits an overage indicator requiring Microsoft Graph resolution.

## Decision

The Entra adapter maps:

- `tid` -> ContextPlane tenant ID;
- `oid` -> stable ContextPlane subject ID;
- `azp` (v2) or `appid` (v1) -> client/application ID;
- `scp` -> delegated scopes;
- `roles` -> roles/application permissions;
- `groups` -> group IDs when the token contains a complete group set.

The reference adapter is single-tenant and requires token `tid` to equal the configured tenant.

Principal-kind rules:

- a delegated token with `scp` is a user principal when no contradictory token type is present;
- `idtyp=app` maps to a service principal by default;
- Entra Agent ID function markers identify an autonomous agent principal;
- an agent acting through its associated user account remains a user principal, with the agent/client application ID preserved.

The adapter deliberately ignores mutable display claims for authorization identity.

Group-overage tokens fail closed until a Graph-backed membership resolver exists.

The reference validator uses a pinned RSA public key. Remote JWKS discovery and key rotation are deferred to a later adapter-hardening change.

## Rationale

This keeps Microsoft-specific token semantics at the adapter boundary while giving downstream policy and resolver code a stable identity model.

Using `tid + oid` avoids authorization decisions based on mutable display identity. Preserving `azp/appid` maintains the actor/client dimension needed for future on-behalf-of policy.

Failing closed on group overage avoids silently treating an incomplete group list as a complete authorization state.

## Consequences

- Entra claim names do not leak into core resolver/policy code;
- applications must configure the expected tenant and API audience;
- app-only tokens need enough type evidence to distinguish them safely;
- group-overage tokens are rejected until Graph expansion is implemented;
- future JWKS/Conditional Access support can replace the pinned-key validation mechanism without changing the normalized principal contract.

## References

- Microsoft Entra access-token claims reference: https://learn.microsoft.com/en-us/entra/identity-platform/access-token-claims-reference
- Microsoft claims validation guidance: https://learn.microsoft.com/en-us/entra/identity-platform/claims-validation
- Microsoft Entra Agent ID token claims: https://learn.microsoft.com/en-us/entra/agent-id/agent-token-claims
