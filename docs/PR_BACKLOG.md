# PR Backlog

This backlog decomposes the implementation plan into reviewable, independently verifiable pull requests.

## Foundation

### PR-001 — Repository and application scaffold

**Status:** verified

Scope:
- Python package;
- FastAPI health endpoint;
- Docker image / Compose service;
- lint, type-check, tests, coverage;
- GitHub Actions.

Acceptance:
- application imports and starts;
- `GET /health` returns a minimal deterministic response;
- CI passes;
- container runs as a non-root user.

### PR-002 — Persistence foundation

**Status:** verified

Dependencies: PR-001

Scope:
- PostgreSQL service;
- application settings;
- SQLAlchemy 2.x;
- Alembic;
- async/sync decision recorded;
- database readiness integration test.

Acceptance:
- migrations apply to an empty database;
- application connects using explicit configuration;
- tests exercise a real PostgreSQL instance in CI;
- credentials are never hard-coded.

## Context registry

### PR-003 — ContextItem and Scope schemas

**Status:** verified

Dependencies: PR-002

Acceptance:
- typed domain, scope, authority, ownership, provenance, effective dates;
- invalid enum/scope values rejected;
- schema migrations and validation tests.

### PR-004 — Immutable versioning and supersession

**Status:** verified

Dependencies: PR-003

Acceptance:
- updates create new versions;
- historical records remain immutable;
- supersession chain is queryable.

### PR-005 — Seed loader

**Status:** verified

Dependencies: PR-003

Acceptance:
- YAML fixture imports the four MVP domains;
- repeated load is idempotent;
- checksums prevent silent duplicates.

## Graph and resolution

### PR-006 — Typed context relations

**Status:** verified

Dependencies: PR-003

Acceptance:
- typed edges can be created and queried;
- tenant boundaries apply to every relation.

### PR-007 — Context resolver

**Status:** verified

Dependencies: PR-004, PR-006

Acceptance:
- resolves organization/team/role/user/task hierarchy;
- returns a deterministic explanation trace.

### PR-008 — Conflict precedence

**Status:** verified

Dependencies: PR-007

Acceptance:
- table-driven tests cover all authority levels and override states.

## Policy and identity

### PR-009 — Policy evaluator

**Status:** verified

Dependencies: PR-008

Acceptance:
- allow, deny, narrow/redact, mandatory-control semantics;
- negative/adversarial tests.

### PR-010 — OIDC principal model

**Status:** verified

Dependencies: PR-001

Acceptance:
- distinct user and agent/service principals;
- invalid tokens fail closed;
- tenant is mandatory.

### PR-011 — Microsoft Entra adapter

**Status:** verified

Dependencies: PR-010

Acceptance:
- Entra claims map to the internal principal model;
- tenant isolation tests;
- contributor documentation does not require production credentials.

## Runtime

### PR-012 — Resolve API

Dependencies: PR-009, PR-011

Acceptance:
- `POST /v1/context/resolve`;
- compact effective context;
- policy decision;
- provenance and explanation.

### PR-013 — Audit trace

Dependencies: PR-012

Acceptance:
- immutable resolution record;
- lookup by resolution ID;
- no secret values in audit payloads.

### PR-014 — Cache boundary

Dependencies: PR-012

Acceptance:
- cache key includes tenant/principal and context/policy version state;
- authoritative updates invalidate stale entries.

## MCP

### PR-015 — MCP server

Dependencies: PR-012

Acceptance:
- `resolve_context` tool;
- contract tests;
- no duplicated resolution logic.

### PR-016 — Domain helper tools

Dependencies: PR-015

Acceptance:
- engineering, brand/presentation, and policy helpers delegate to the same resolver.

## Client demos

### PR-017 — Coding-agent demo

Dependencies: PR-015

Acceptance:
- repository-specific engineering standards resolved through MCP.

### PR-018 — Copilot Studio demo

Dependencies: PR-015, PR-011

Acceptance:
- identity-aware brand/presentation context;
- docs explicitly distinguish orchestration from enforcement.

## Hardening

### PR-019 — Adversarial policy suite

Dependencies: PR-018

Acceptance:
- privilege escalation;
- prompt injection;
- stale context;
- cross-tenant leakage;
- context poisoning.

### PR-020 — Evaluation report

Dependencies: PR-019

Acceptance:
- reproducible latency, retrieval-size, rule-accuracy, policy-violation, and client-consistency benchmarks.
