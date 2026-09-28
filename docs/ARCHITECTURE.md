# Architecture

## Goal

ContextPlane sits between AI clients and authoritative organizational context. Its core responsibility is to produce a governed, identity-aware context bundle and an auditable decision.

## Logical architecture

```text
Sources
  |
  v
Context Registry ---- Provenance / Versioning
  |
  v
Context Graph
  |
  +----------- Policy Engine
  |
  +----------- Identity Resolver
  |
  v
Context Resolver ---- Audit Logger
  |
  +---- Resolution Cache
  |
  +---- MCP
  +---- REST
  +---- SDK
```

## Reference stack

The MVP optimizes for readability and reproducibility rather than scale.

- Python 3.12+
- FastAPI
- PostgreSQL
- Pydantic
- Alembic
- OIDC/JWT
- Microsoft Entra reference adapter
- pytest
- Docker Compose
- GitHub Actions

Start with typed graph edges in PostgreSQL. Introduce a graph database only if real traversal requirements justify it.

## Core modules

```text
src/
  api/
  auth/
  context_registry/
  context_graph/
  resolver/
  policy/
  provenance/
  audit/
  interfaces/
    mcp/
    rest/
  adapters/
    entra/
    databricks/
    microsoft/
  models/
  evals/
```

## Runtime sequence

1. Client calls `resolve_context` with request data and identity token.
2. Gateway validates user and/or agent identity.
3. Identity resolver maps claims to the internal principal model.
4. Policy engine determines allowed scopes and controls.
5. Gateway reads the tenant context revision and next effective-time boundary.
6. Candidate resolver uses an identity/version-aware cache or queries applicable context candidates.
7. Conflict/precedence rules produce the effective set.
8. Gateway loads current provenance and writes a new immutable audit record.
9. Gateway returns a compact context bundle, policy decision, provenance, and explanation trace.

## Context resolution dimensions

Candidate selection may use:

- tenant;
- domain;
- business unit;
- team;
- role;
- user;
- agent;
- application;
- repository;
- resource;
- task;
- audience;
- environment;
- effective date.

## Precedence

Resolution should be deterministic.

Suggested precedence:

1. mandatory-control precedence;
2. authority level;
3. explicit scope specificity;
4. source authority;
5. effective date/version;
6. user preference only where override is permitted.

## Resolution cache boundary

The reference cache stores candidate-resolution results only. Cache reuse requires identical principal/request state, context revision, and policy fingerprint, and entries expire before the next known context effective-time transition.

Policy evaluation, precedence, provenance, and audit creation still run on every request. The reference implementation is bounded and process-local; a distributed cache must preserve the same invariants.

See ADR-013 for the exact cache key and invalidation model.

## Mandatory context vs. hard enforcement

ContextPlane can guarantee which rule it returns and how it labels it. It cannot guarantee that an arbitrary downstream model obeys a textual instruction.

For sensitive operations, enforcement must live at a resource or authorization boundary that the model cannot bypass.

## Source adapters

Source systems remain authoritative. The gateway stores normalized context records and references rather than necessarily copying full source documents.

Adapters should expose:

- fetch/refresh;
- source identifier;
- checksum;
- owner;
- update time;
- version/effective date;
- parsing into candidate context records.

## Deployment modes

### Local

Docker Compose + PostgreSQL + test OIDC issuer.

### Enterprise reference

Containerized service behind enterprise ingress, OIDC with Entra, managed PostgreSQL, centralized audit/logging, optional Redis.

### Future federated

Context domains can remain under separate owners and be resolved through a federated gateway without centralizing every source.
