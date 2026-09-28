# ADR-013 — Cache Candidate Resolution Only Across Identical Identity and Version State

**Status:** Accepted for MVP  
**Date:** 2026-09-28

## Context

Context resolution is a natural caching target, but ContextPlane results depend on authenticated identity, request scope, policy configuration, context-version state, and effective-time windows.

Caching the final API response would also incorrectly reuse per-request audit identifiers and could bypass policy/provenance work that should remain fresh.

A database write is not the only way results can change: an existing context item can become effective or expire as time advances.

## Decision

The reference cache stores **candidate-resolution results only**.

Policy evaluation, conflict precedence, provenance loading, and audit creation continue to execute for every request.

A cache key is an opaque SHA-256 digest over:

- tenant, subject, principal kind, and client/application identity;
- normalized principal roles, groups, and scopes;
- complete resolver scope;
- requested policy-constrained domains and keys;
- the tenant context revision;
- a deterministic fingerprint of the configured policy rules.

ContextPlane maintains a per-tenant monotonic context revision in PostgreSQL. A database trigger increments the revision on every `INSERT`, `UPDATE`, or `DELETE` to `context_items`. Existing tenants are backfilled during migration.

Cache entries expire at the earlier of:

1. the configured cache TTL; or
2. the next known `effective_from` or `effective_to` timestamp for the tenant.

On a cache hit, the candidate set is reused but the request receives a fresh evaluation timestamp, conflict-precedence calculation, provenance lookup, and resolution audit.

The initial implementation is a bounded, thread-safe, process-local LRU. Distributed caching is explicitly deferred.

## Rationale

This boundary captures the expensive/repetitive candidate-selection work without caching authorization decisions or audit records.

The database revision token makes invalidation deterministic across normal repository writes and direct database mutations. Temporal expiry closes the separate stale-data path where context changes applicability without any write.

Opaque digest keys avoid exposing raw identities and selectors in cache-key surfaces.

## Consequences

- every runtime request still evaluates current policy rules;
- every runtime request still receives a unique resolution/audit ID;
- context values remain present in process memory for the duration of a cache entry and must be treated as sensitive runtime state;
- old entries are not actively deleted on revision change, but their revision-bearing keys can no longer be selected and normal LRU eviction removes them;
- policy persistence may eventually replace rule hashing with a durable policy revision token;
- a production distributed cache must preserve the same identity/version/temporal invariants;
- database-owner tampering with the revision table is outside the application trust boundary.
