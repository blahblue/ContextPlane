# Implementation Plan

The implementation should follow a verification-first sequence.

## Phase 0 — Foundation

**Status: verified in PR-001.**

Deliver:

- Python project scaffold;
- FastAPI health endpoint;
- Docker Compose;
- GitHub Actions;
- lint/type/test configuration.

Exit gate: clean clone -> one documented command starts the service and CI passes.

Verification: GitHub Actions run 36442725339 passed install, lint, strict type-checking, and tests. A stranger-diff review also resulted in a non-root container hardening change.

## Phase 1 — Persistence + context registry

**Persistence foundation: verified in PR-002. ContextItem/Scope/provenance schema: verified in PR-003. Immutable versioning/supersession: verified in PR-004. Seed loading remains planned for PR-005.**

Persistence verification: migrations applied to an empty PostgreSQL 16 service in GitHub Actions; configuration validation and real-database readiness tests passed.

Deliver:

- PostgreSQL service and application database configuration;
- Alembic migrations;

- ContextItem schema;
- Scope schema;
- source/provenance schema;
- authority levels;
- CRUD API;
- immutable versioning;
- YAML seed loader. **Verified in PR-005:** safe YAML parsing, canonical checksums, stable seed identity, idempotent reload, and immutable supersession.

Exit gate: no update silently mutates historical records.

Versioning verification: PR-004 uses insert-only repository operations plus tenant/logical lineage constraints; fork, cross-tenant lineage, stale predecessor, and invalid lineage-shape cases are covered against real PostgreSQL.

## Phase 2 — Context graph + resolver

**Graph foundation: verified in PR-006. Candidate resolver: verified in PR-007. Conflict precedence: verified in PR-008.**

Deliver:

- typed relations; **verified in PR-006**
- candidate selection; **verified in PR-007**
- hierarchy across org/team/role/user/task; **scope matching foundation verified in PR-007**
- deterministic conflict resolution; **verified in PR-008**
- explanation trace. **candidate explanation trace verified in PR-007**

Exit gate: table-driven tests cover precedence.

## Phase 3 — Policy

**Core policy evaluator: verified in PR-009. Identity-aware conditions and resource enforcement remain later work.**

Deliver:

- allow/deny; **verified in PR-009**
- override rules; **admission authority and deny-safe ties verified in PR-009**
- mandatory controls; **verified in PR-009**
- sensitivity classes;
- policy decision result. **verified in PR-009**

Exit gate: personal preferences cannot override mandatory controls.

## Phase 4 — Identity

**Provider-neutral OIDC principal model: verified in PR-010. Microsoft Entra adapter: verified in PR-011.**

Deliver:

- OIDC abstraction; **verified in PR-010**
- local test issuer;
- Entra reference adapter; **verified in PR-011**
- user + agent principal model; **verified in PR-010**
- tenant isolation. **generic tenant requirement verified in PR-010; Entra tenant mapping verified in PR-011**

Exit gate: cross-tenant requests fail closed.

## Phase 5 — Runtime API

**Authenticated REST resolution path: verified in PR-012. Immutable runtime audit: verified in PR-013. Identity/version-aware cache boundary: verified in PR-014.**

Deliver:

- `POST /v1/context/resolve`; **verified in PR-012**
- compact context packaging; **verified in PR-012**
- provenance; **safe runtime provenance verified in PR-012**
- audit log; **verified in PR-013**
- cache boundary. **verified in PR-014**

Exit gate: identity + policy + graph + audit succeed end to end.

## Phase 6 — MCP

**Authenticated shared-runtime MCP server: verified in PR-015. Domain helper tools: verified in PR-016.**

Deliver:

- MCP server wrapping the same resolver; **verified in PR-015 via protocol-independent runtime service**
- `resolve_context`; **verified in PR-015**
- context-specific helper tools; **verified in PR-016**
- contract tests.

Exit gate: two clients produce equivalent resolver results.

PR-016 verification confirms engineering, brand/presentation, and security-policy helpers remain constrained views over the same governed runtime. Repository/resource selectors are applicability dimensions, not authorization credentials.

## Phase 7 — Copilot Studio demo

**Status: verified in PR-018.**

Deliver:

- reproducible integration guide; **verified against current Microsoft Copilot Studio MCP documentation**
- sample presentation/proposal scenario; **included in examples/copilot-studio**
- identity-aware brand/presentation context; **verified across marketing-user vs engineering-user principals**
- documented orchestration-vs-enforcement boundary; **explicitly documented in the demo guide**
- selective MCP tool guidance and Power Platform data-policy notes; **documented for the current Copilot Studio integration path**

Exit gate: changing an authoritative rule changes output without editing embedded client prompts.

Verification: the exact demo corpus is exercised through the real MCP helper/shared runtime. CI verifies cross-user isolation, cross-tenant isolation, shared brand/presentation context, and cache invalidation after authoritative context supersession. Live Copilot Studio OAuth/tenant integration remains an operator-run external step because CI does not control a Microsoft tenant.

## Phase 8 — Coding-agent demo

**Status: verified in PR-017.**

Deliver:

- Cursor-compatible MCP configuration example; **verified against current Cursor MCP configuration documentation**
- repository-scoped engineering context; **verified with checkout-api vs catalog-api**
- security rules; **verified through get_policy_context for checkout-api**
- sample coding task; **included in examples/coding-agent**

Exit gate: different repositories receive different context from the same gateway.

Verification: the exact demo YAML fixture is loaded through the production seed path and exercised through the real MCP helper tools. CI proves repository isolation and the mandatory checkout security-control result. Cursor configuration is statically validated and documented; live Cursor/Entra OAuth login is intentionally an operator-run demo rather than a CI dependency.

## Phase 9 — Governance + audit

Deliver:

- owner metadata;
- publication state;
- effective dates;
- decision explanation;
- audit query API.

Exit gate: every result is attributable to source, owner, version, and policy path.

## Phase 10 — Evaluation

Deliver:

- golden scenarios;
- latency benchmark;
- over-retrieval metric;
- policy-violation tests;
- stale-context tests;
- client consistency tests.

Exit gate: reproducible benchmark report checked into the repository.

## Recommended sequencing

Do **not** begin with broad SaaS connectors. Seed the first corpus with repository-owned YAML/JSON fixtures so the resolver and policy model can be proven independently of connector complexity.
