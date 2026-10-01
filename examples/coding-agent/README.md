# Coding-agent demo

This demo proves that one MCP-capable coding client can receive different governed engineering context for different repositories without embedding repository rules in the agent prompt.

## What it demonstrates

```text
Cursor / coding agent
        |
        v
get_engineering_context(repository=...)
get_policy_context(repository=...)
        |
        v
shared ContextPlane runtime
        |
   +----+----+
   |         |
checkout   catalog
context    context
```

The same authenticated client and the same MCP server return different applicable context based on the repository selector.

Repository and resource selectors are applicability dimensions, not authorization credentials.

## 1. Load the demo context

The fixture is:

```text
examples/coding-agent/context.yaml
```

Load it through the existing ContextPlane seed-loader workflow into a local database. The fixture uses tenant `coding-demo-org`.

The corpus contains:

- one production-wide engineering testing standard;
- checkout-specific FastAPI/SQLAlchemy conventions;
- catalog-specific Django conventions;
- a checkout-specific mandatory security control for secret handling.

## 2. Run ContextPlane MCP

Configure the normal ContextPlane MCP environment, including the database and Entra settings documented in [../../docs/MCP.md](../../docs/MCP.md).

Set the public MCP endpoint for the coding client:

```bash
export CONTEXTPLANE_MCP_URL="https://contextplane.example.com/mcp"
export CONTEXTPLANE_CURSOR_CLIENT_ID="<your-Entra-public-client-id>"
```

Then run:

```bash
contextplane-mcp
```

## 3. Configure Cursor

Copy this demo's project MCP configuration into the repository you want Cursor to use:

```text
.cursor/mcp.json
```

The checked-in example uses Cursor environment-variable interpolation and static OAuth client configuration. Do not commit OAuth client secrets.

For a desktop/public client, register the Cursor OAuth callback URI with the Entra client application. Cursor's current documentation lists:

```text
http://localhost:8787/callback
```

If the same client is used from Cursor web/agents, also register:

```text
https://www.cursor.com/agents/mcp/oauth/callback
```

Then authenticate the MCP server through Cursor. The Cursor CLI can use:

```bash
agent mcp list
agent mcp login contextplane
agent mcp list-tools contextplane
```

You should see:

- `resolve_context`
- `get_engineering_context`
- `get_brand_presentation_context`
- `get_policy_context`

Cursor MCP reference: https://cursor.com/docs/mcp

## 4. Run the sample task

Use [sample-task.md](sample-task.md).

For `checkout-api`, the engineering helper should return:

- `engineering.testing.required`
- `engineering.checkout.service_conventions`

The policy helper should additionally return:

- `security.checkout.secret_handling`

For `catalog-api`, the engineering helper should return:

- `engineering.testing.required`
- `engineering.catalog.service_conventions`

It must not return checkout-specific engineering context.

## 5. Prove context is operational

Change an authoritative checkout rule in `context.yaml`, reload the seed, and call the helper again.

The coding-agent context should change without editing:

- the sample task;
- Cursor's MCP configuration;
- the MCP tool definition;
- the agent's embedded prompt.

That is the core demo: organizational context lives in ContextPlane rather than being copied into every coding client.

## Security boundary

This demo is about context resolution, not repository authorization.

A model-provided value such as `repository="checkout-api"` selects applicable context. It does not grant access to GitHub, source code, deployment systems, or another protected resource.

Those systems still require enforceable authorization at their own boundary.
