# Implementation Plan

The implementation should follow a verification-first sequence.

## Phase 0 — Foundation

Deliver:

- Python project scaffold;
- FastAPI health endpoint;
- PostgreSQL + migrations;
- Docker Compose;
- GitHub Actions;
- lint/type/test configuration.

Exit gate: clean clone -> one documented command starts the system and CI passes.

## Phase 1 — Context registry

Deliver:

- ContextItem schema;
- Scope schema;
- source/provenance schema;
- authority levels;
- CRUD API;
- immutable versioning;
- YAML seed loader.

Exit gate: no update silently mutates historical records.

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
