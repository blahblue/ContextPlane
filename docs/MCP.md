# MCP Server

ContextPlane exposes its governed runtime through an MCP v2 `resolve_context` tool.

MCP is a transport adapter. The tool delegates to the same protocol-independent runtime service used by the REST API.

## Tool

```text
resolve_context(
  domains,
  keys?,
  task?,
  audience?,
  environment?
)
```

Identity is intentionally **not** a tool argument.

For remote Streamable HTTP, tenant, subject, principal kind, client/application identity, roles, groups, and scopes come from the authenticated bearer-token boundary.


## Domain helper tools

ContextPlane also exposes narrower semantic helpers. These are constrained views over the same shared runtime, not separate retrieval implementations.

```text
get_engineering_context(
  keys?,
  task?,
  environment?,
  repository?,
  resource?
)

get_brand_presentation_context(
  keys?,
  task?,
  audience?,
  environment?,
  resource?
)

get_policy_context(
  keys?,
  task?,
  audience?,
  environment?,
  repository?,
  resource?
)
```

The helper domain sets are fixed by the server:

- `get_engineering_context` -> engineering;
- `get_brand_presentation_context` -> brand + presentation;
- `get_policy_context` -> security context, including security-policy and mandatory-control context stored in the registry.

A helper invocation still performs authentication, policy evaluation, context resolution, precedence, cache validation, provenance loading, and audit creation through `resolve_context_runtime`.

Repository and resource are applicability selectors. They are not identity claims or authorization grants. A sensitive underlying resource still needs an enforceable authorization boundary.

## Reference authentication

The reference server uses Microsoft Entra through the existing ContextPlane Entra validator.

Required configuration:

```text
CONTEXTPLANE_DATABASE_URL
CONTEXTPLANE_ENTRA_TENANT_ID
CONTEXTPLANE_ENTRA_ISSUER
CONTEXTPLANE_ENTRA_AUDIENCE
CONTEXTPLANE_ENTRA_PUBLIC_KEY_PEM
CONTEXTPLANE_MCP_RESOURCE_SERVER_URL
```

The Entra application registration must issue either:

- delegated scope `context.resolve`; or
- application role `context.resolve`.

The MCP adapter validates the Entra API audience itself. The public MCP endpoint URL is published as OAuth protected-resource metadata, but it is not substituted for the Entra token audience.

## Run

```bash
contextplane-mcp
```

The reference CLI uses Streamable HTTP with stateless legacy serving and JSON responses.

Modern MCP 2026-07-28 requests are sessionless by protocol. Stateless legacy serving is also used so older session-based connections do not carry authenticated request identity across multiple HTTP requests.

## Trust boundaries

### Remote Streamable HTTP

Bearer authentication is enforced by the MCP HTTP resource-server middleware before the tool runs.

The verified access token carries a normalized ContextPlane `Principal` produced by the Entra adapter. The tool reads that principal from authenticated request context.

### In-process / stdio

MCP bearer middleware does not protect in-process or stdio transports. Their security boundary is the process that launches/embeds the server.

The `principal_provider` constructor argument exists only as an explicit embedding/testing seam and cannot be combined with the remote HTTP auth configuration.

## Tool errors

Handled governance/policy failures return generic MCP `ToolError` messages with the durable ContextPlane `resolution_id`.

The tool does not expose internal policy bodies, token-validation errors, source URIs, or context not authorized for the principal.

## SDK

The repository targets the official MCP Python SDK major version 2:

```text
mcp>=2.0,<3.0
```

The v2 server class is `MCPServer`.

## References

- MCP Python SDK authorization: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/run/authorization.md
- MCP Python SDK v2 migration guide: https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md
