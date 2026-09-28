# Architecture Decision Records

ADRs capture decisions that materially constrain the implementation.

Current ADRs:

- [ADR-001 — MCP is an interface, not the product](001-mcp-is-an-interface.md)
- [ADR-002 — Microsoft Entra is the reference identity provider](002-entra-reference-idp.md)
- [ADR-003 — Separate mandatory context from hard enforcement](003-context-vs-enforcement.md)
- [ADR-004 — Use synchronous SQLAlchemy for the initial persistence layer](004-sync-sqlalchemy.md)
- [ADR-005 — Relations target logical context identities with immutable version anchors](005-logical-relation-anchors.md)

New ADRs should use a short sequential number and include:

- status;
- date;
- context;
- decision;
- rationale;
- consequences.
