# Sample Copilot Studio scenario

Create an executive-facing proposal summary for an external client.

Before drafting the proposal:

1. Invoke `get_brand_presentation_context` with:
   - `audience="executive"`
   - `task="draft external executive proposal"`
2. Use the returned brand and presentation context as the authoritative ContextPlane guidance for the draft.
3. Keep the returned `resolution_id` available for audit/debugging.

Expected behavior:

- both authenticated users receive the shared executive presentation standard;
- user-specific presentation context differs based on the authenticated ContextPlane principal;
- external brand context is returned when the request uses the external audience selector in a separate call or when the demo is configured for that audience.

For an external-brand-specific pass, invoke:

`get_brand_presentation_context(audience="external", task="draft external executive proposal")`

Do not place tenant, user, agent, role, group, or client identity in tool arguments. Identity comes from the authenticated MCP connection.
