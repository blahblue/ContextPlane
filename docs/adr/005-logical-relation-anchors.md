# ADR-005 — Relations Target Logical Context Identities with Immutable Version Anchors

**Status:** Accepted for MVP  
**Date:** 2026-09-28

## Context

Context items are immutable versions grouped by a stable `logical_id`. A graph relation should normally survive when either endpoint is superseded, so binding an edge only to a specific version ID would make relations stale after every context update.

At the same time, tenant boundaries and endpoint existence should be enforced by PostgreSQL rather than only by application code.

## Decision

A context relation stores both:

- the source and target `logical_id`, which define graph semantics across versions; and
- immutable source/target anchor version IDs, used in composite foreign keys with `tenant_id`.

The anchor records prove that each logical endpoint existed in the same tenant when the relation was created. Graph queries use logical IDs, so later context versions do not require rewriting the edge.

## Rationale

This provides durable logical relations without introducing a separate logical-node table before the graph requires one, while still retaining database-level tenant-aware referential integrity.

## Consequences

- context item versions remain immutable;
- relation rows do not need to change when an endpoint is superseded;
- deleting anchor versions is restricted;
- relation creation resolves the latest endpoint versions only as immutable referential anchors;
- if a future graph needs first-class non-context entities, the node model will require a new ADR and migration.
