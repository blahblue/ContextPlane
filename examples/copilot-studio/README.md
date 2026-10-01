# Copilot Studio demo

This demo shows Microsoft Copilot Studio consuming governed brand and presentation context from ContextPlane through MCP.

The scenario is intentionally narrow: two authenticated users ask the same agent for executive presentation guidance. ContextPlane returns shared organizational standards plus the context that applies to the authenticated user.

## Current Copilot Studio path

As of 2026-10-01, Microsoft's current Copilot Studio documentation supports adding an existing MCP server directly to an agent created in the new experience:

1. open the agent;
2. go to **Build**;
3. open **Tools**;
4. select **Add** -> **Model Context Protocol (MCP)**;
5. enter the MCP server name, description, reachable HTTPS server URL, and a supported authentication configuration;
6. save the server and review the tools exposed by the MCP handshake;
7. use **Preview** and the activity trace to verify which tool was invoked and what it returned.

The Microsoft feature is documented as preview and can change. Re-check the linked Microsoft documentation before a live demo.

Microsoft references:
- https://learn.microsoft.com/en-us/microsoft-copilot-studio/agents-experience/tools-add-mcp-server
- https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-add-components-to-agent
- https://learn.microsoft.com/en-us/microsoft-copilot-studio/mcp-create-new-server

## Demo architecture

```text
Copilot Studio agent
        |
        | authenticated MCP
        v
ContextPlane MCP server
        |
        v
get_brand_presentation_context(...)
        |
        v
shared governed runtime
   | identity
   | policy
   | resolver
   | precedence
   | cache
   | provenance
   | audit
        |
        v
effective brand/presentation context
```

The MCP tool never accepts tenant/user/agent/client identity arguments. ContextPlane derives identity from its authenticated MCP boundary.

## 1. Load demo context

Configure `CONTEXTPLANE_DATABASE_URL`, then run:

```bash
python examples/copilot-studio/load_seed.py
```

The fixture uses tenant `copilot-demo-org`.

It contains:

- a shared external brand-voice standard;
- a shared executive presentation standard;
- a marketing-user presentation preference;
- an engineering-user presentation preference.

## 2. Run the ContextPlane MCP server

Use the authenticated MCP configuration documented in [../../docs/MCP.md](../../docs/MCP.md).

The public server must be reachable from Copilot Studio over HTTPS.

For the reference ContextPlane implementation, the token reaching the MCP server must validate through the configured Microsoft Entra tenant/API boundary and carry `context.resolve` as a delegated scope or application role.

## 3. Add ContextPlane to Copilot Studio

In the new Copilot Studio experience:

- create/open an agent;
- Build -> Tools -> Add -> Model Context Protocol (MCP);
- Name: `ContextPlane`;
- Description: `Resolve governed organizational brand, presentation, engineering, and security context for the authenticated caller.`;
- Server URL: your public ContextPlane MCP endpoint;
- Authentication: configure a method that produces the Entra access token expected by your ContextPlane deployment;
- save and verify these tools appear:
  - `resolve_context`
  - `get_engineering_context`
  - `get_brand_presentation_context`
  - `get_policy_context`.

For this demo, turn off **Allow all** and enable only `get_brand_presentation_context`. Copilot Studio currently supports enabling/disabling individual tools from an MCP server, which keeps the agent's available tool surface aligned with the scenario.

Microsoft's direct-MCP documentation describes supported authentication configuration generically rather than guaranteeing one specific Entra flow for every tenant/runtime combination. OAuth 2.0 is a supported MCP authentication option, but validate the actual token received by ContextPlane before presenting the identity-aware portion as production-ready.

Copilot Studio MCP connectivity is implemented through Power Platform connector infrastructure. Microsoft documents that Power Platform data policies can regulate access to MCP servers and their tools. Treat those platform controls as an additional governance layer, not a replacement for ContextPlane's own authentication and policy checks.

## 4. Run the scenario

Use [sample-task.md](sample-task.md).

For the executive presentation call:

```text
get_brand_presentation_context(
  audience="executive",
  task="draft external executive proposal"
)
```

The shared result includes:

- `presentation.executive.structure`

For authenticated subject `marketing-user`, ContextPlane additionally returns:

- `presentation.user.marketing`

For authenticated subject `engineering-user`, it instead returns:

- `presentation.user.engineering`

The user identity is not supplied in the tool call.

For the external-brand call:

```text
get_brand_presentation_context(
  audience="external",
  task="draft external executive proposal"
)
```

the result includes:

- `brand.external.voice`

## 5. Verify in Copilot Studio

In Preview, ask a question that requires the brand/presentation tool. Use Copilot Studio's activity trace to confirm the tool invocation, selectors, returned context, and ContextPlane resolution ID.

Do not infer identity propagation from the natural-language answer alone. Verify what token/principal reached ContextPlane.

## Orchestration is not enforcement

This distinction is part of the demo, not a footnote.

Copilot Studio's orchestrator can decide whether to call an MCP tool based on tool names, descriptions, and agent instructions. That makes ContextPlane context available to generation. It does **not** prove that a model will always call the tool or obey every returned instruction.

ContextPlane enforces:

- authentication of the MCP caller;
- which context the principal is authorized to receive;
- deterministic resolution and precedence;
- auditability of the resolution.

ContextPlane does **not**, by merely returning a mandatory instruction, force the language model's final prose to comply.

For controls that must be enforceable, put the boundary around the protected action or data, or add deterministic validation before/after generation. Do not treat a prompt instruction such as "always call ContextPlane" as a security control.

## CI verification boundary

The repository can deterministically test:

- the exact seed corpus;
- two authenticated principals receiving different user-scoped context;
- shared organizational context being returned to both;
- no identity being supplied through helper arguments;
- authoritative seed changes changing later resolution results;
- all calls going through the same MCP/runtime/policy/audit implementation.

CI cannot log into your Copilot Studio tenant or prove a particular tenant's external authentication configuration. The live Copilot Studio connection remains an operator-run integration step.
