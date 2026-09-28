# ADR-014 — Keep MCP as an Authenticated Adapter over the Shared Runtime

**Status:** Accepted  
**Date:** 2026-09-28

## Context

ContextPlane needs to serve MCP-capable clients without creating a parallel implementation of context resolution.

Duplicating policy, candidate selection, conflict precedence, provenance, cache, or audit logic inside MCP handlers would allow REST and MCP to drift and would make MCP itself part of the product's core architecture.

MCP tool arguments are model-controlled input and cannot be trusted as an identity source.

## Decision

ContextPlane extracts runtime orchestration into a protocol-independent service.

Both REST and MCP delegate to that service.

The MCP `resolve_context` tool exposes only task/context selectors:

- domains;
- optional keys;
- task;
- audience;
- environment.

Tenant, user/agent/service identity, client application, roles, groups, and scopes are never model-visible tool arguments.

For remote Streamable HTTP:

1. MCP bearer middleware validates the access token through a ContextPlane-backed `TokenVerifier`;
2. the existing Entra validator verifies signature, issuer, audience, time, and tenant;
3. the MCP adapter requires `context.resolve` as either a delegated scope or application role;
4. the normalized ContextPlane `Principal` is attached to verified access-token claims;
5. the tool retrieves that authenticated principal from request context and calls the shared runtime.

The reference server uses `stateless_http=True` for the legacy MCP transport path. Modern 2026-07-28 requests are already sessionless.

In-process and stdio MCP transports are explicitly outside the bearer-authentication boundary; their process/launcher is the trust boundary.

## Rationale

This preserves the architectural rule that MCP is an interface rather than the product.

It also prevents a model from selecting its own tenant or principal while retaining a testable seam for in-process integration tests.

Reusing ContextPlane's Entra validation avoids a second interpretation of enterprise identity.

## Consequences

- transport adapters remain thin;
- shared runtime errors must be mapped separately into HTTP and MCP transport semantics;
- remote MCP deployment requires the public MCP resource URL plus Entra configuration;
- an Entra application registration needs a `context.resolve` delegated scope or app role;
- production key discovery/rotation remains an identity-adapter concern;
- future domain-specific MCP tools must delegate to the same runtime/policy primitives rather than recreate them.

## References

- MCP Python SDK authorization: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/authorization.md
- MCP Python SDK v2 migration: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md
