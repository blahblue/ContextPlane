# Architecture Decision Records

ADRs capture decisions that materially constrain the implementation.

Current ADRs:

- [ADR-001 — MCP is an interface, not the product](001-mcp-is-an-interface.md)
- [ADR-002 — Microsoft Entra is the reference identity provider](002-entra-reference-idp.md)
- [ADR-003 — Separate mandatory context from hard enforcement](003-context-vs-enforcement.md)
- [ADR-004 — Use synchronous SQLAlchemy for the initial persistence layer](004-sync-sqlalchemy.md)
- [ADR-005 — Relations target logical context identities with immutable version anchors](005-logical-relation-anchors.md)
- [ADR-006 — Resolve version applicability before scope specificity](006-resolution-version-scope-order.md)
- [ADR-007 — Resolve context conflicts with authority, specificity, and explicit override](007-conflict-precedence.md)
- [ADR-008 — Separate domain admission from monotonic key narrowing](008-policy-admission-narrowing.md)
- [ADR-009 — Normalize provider tokens into distinct ContextPlane principals](009-provider-neutral-principal.md)
- [ADR-010 — Map Microsoft Entra access tokens to immutable ContextPlane identity](010-entra-claim-mapping.md)
- [ADR-011 — Derive runtime identity scope from the authenticated principal](011-runtime-identity-scope.md)
- [ADR-012 — Persist resolution audits as append-only, payload-minimized records](012-append-only-resolution-audit.md)

New ADRs should use a short sequential number and include:

- status;
- date;
- context;
- decision;
- rationale;
- consequences.
