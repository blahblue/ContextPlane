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

Deliver:

- typed relations;
- candidate selection;
- hierarchy across org/team/role/user/task;
- deterministic conflict resolution;
- explanation trace.

Exit gate: table-driven tests cover precedence.

## Phase 3 — Policy

Deliver:

- allow/deny;
- override rules;
- mandatory controls;
- sensitivity classes;
- policy decision result.

Exit gate: personal preferences cannot override mandatory controls.

## Phase 4 — Identity

Deliver:

- OIDC abstraction;
- local test issuer;
- Entra reference adapter;
- user + agent principal model;
- tenant isolation.

Exit gate: cross-tenant requests fail closed.

## Phase 5 — Runtime API

Deliver:

- `POST /v1/context/resolve`;
- compact context packaging;
- provenance;
- audit log;
- cache boundary.

Exit gate: identity + policy + graph + audit succeed end to end.

## Phase 6 — MCP

Deliver:

- MCP server wrapping the same resolver;
- `resolve_context`;
- context-specific helper tools;
- contract tests.

Exit gate: two clients produce equivalent resolver results.

## Phase 7 — Copilot Studio demo

Deliver:

- reproducible integration guide;
- sample presentation/proposal scenario;
- documented orchestration-vs-enforcement boundary.

Exit gate: changing an authoritative rule changes output without editing embedded client prompts.

## Phase 8 — Coding-agent demo

Deliver:

- Cursor-compatible MCP configuration example;
- repository-scoped engineering context;
- security rules;
- sample coding task.

Exit gate: different repositories receive different context from the same gateway.

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
