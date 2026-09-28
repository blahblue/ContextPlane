# ADR-012 — Persist Resolution Audits as Append-Only, Payload-Minimized Records

**Status:** Accepted for MVP  
**Date:** 2026-09-28

## Context

ContextPlane makes runtime decisions that combine authenticated identity, policy evaluation, context resolution, conflict precedence, and provenance.

Those decisions need to be explainable after the request completes, but an audit log can become a second sensitive data store if it copies bearer tokens, context payloads, source documents, selector values, or other request content.

Audit history also loses evidentiary value if application code can silently rewrite prior records.

## Decision

Every handled authenticated resolution outcome is assigned a unique `resolution_id` and persisted as a dedicated resolution audit record.

Audit records contain only the minimum metadata needed to reconstruct the decision boundary:

- tenant;
- normalized principal kind and actor identifiers;
- evaluation time;
- requested domains and requested-key count;
- names of contextual selector dimensions, not their values;
- policy decision and decisive rule IDs;
- IDs of context versions considered;
- IDs/logical IDs/domain/version for returned context;
- conflict suppression record references;
- outcome and a stable error code when applicable.

Audit records deliberately do **not** contain:

- bearer tokens;
- context values;
- payload contents;
- prompt text;
- source URIs;
- policy rule bodies/reasons;
- task, audience, or environment values.

PostgreSQL enforces append-only semantics with a trigger that rejects `UPDATE` and `DELETE` operations on the audit table.

The caller receives the `resolution_id` in a successful/denied response body. Audited error responses expose the same identifier in the `X-ContextPlane-Resolution-ID` header.

The initial lookup API is deliberately conservative: a principal may retrieve only an audit record created by the exact same tenant, subject, principal kind, and client identity. Privileged administrative audit search is deferred.

## Rationale

This gives ContextPlane durable decision provenance without duplicating organizational context or authentication secrets into a second database surface.

Database-enforced immutability protects against accidental application mutation and makes the invariant independently testable.

Exact-actor lookup is narrower than typical enterprise audit administration, but it avoids introducing an administrator authorization model before ContextPlane has one.

## Consequences

- a resolve request that successfully reaches a handled terminal outcome must commit its audit before returning;
- database unavailability may prevent both the runtime response and its required audit from completing;
- audit storage still contains enterprise identifiers and therefore remains sensitive operational data;
- privileged cross-user audit search requires an explicit future authorization model;
- external WORM/SIEM sinks, retention rules, log signing/chaining, and compliance exports remain future work;
- database owners can still perform privileged maintenance outside the application trust boundary, so the trigger is an application/database invariant rather than a claim of tamper-proof storage.
