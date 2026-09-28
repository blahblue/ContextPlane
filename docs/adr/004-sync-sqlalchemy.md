# ADR-004 — Use Synchronous SQLAlchemy for the Initial Persistence Layer

**Status:** Accepted for MVP  
**Date:** 2026-09-28

## Context

ContextPlane needs PostgreSQL persistence before the workload shape is known. Introducing asynchronous SQLAlchemy would add separate async driver, session, migration, and test concerns before the resolver has demonstrated a need for high-concurrency database access.

## Decision

Use SQLAlchemy 2.x with the synchronous `psycopg` driver for the initial persistence layer.

## Rationale

- simpler migration and testing path;
- deterministic transaction semantics;
- fewer framework-specific dependencies;
- database operations are expected to be short and bounded in the MVP;
- the repository can introduce an async adapter later without changing the context schema.

## Consequences

- request handlers that perform database work must avoid long-running transactions;
- performance testing should identify whether synchronous DB access becomes a bottleneck;
- a future async migration requires an explicit ADR rather than an incidental refactor.
