# ADR-018 — Derive Publication Identity Server-Side and Persist Actor Provenance

**Status:** Accepted  
**Date:** 2026-10-02

## Context

PR-024 defined explicit publication permissions for each authority level, but the MVP still relied on operator-controlled seed loading for writes.

An authenticated write API introduces new risks:

- tenant or publisher identity injection through the request body;
- replay creating duplicate immutable versions;
- publication audit records containing sensitive context payloads;
- semantic owner/source metadata being confused with the authenticated actor;
- stale predecessor supersession;
- changing authority level during supersession to bypass future approval workflow.

## Decision

Authenticated publication uses two HTTP operations:

- `POST /v1/context/items`;
- `POST /v1/context/items/{previous_id}/supersede`.

The external request contract does **not** contain:

- tenant ID;
- publisher subject/kind/client;
- publication permission;
- checksum;
- audit actor fields.

Tenant and publisher identity come only from the normalized authenticated Principal.

The server derives a canonical SHA-256 checksum after injecting the authenticated tenant.

Because this path is itself the authenticated API authoring path, the persisted source type is server-fixed to `api`. A caller may provide a descriptive source identifier/URI, but cannot claim that an API write was independently attested by a Git, SharePoint, Drive, Databricks, or Fabric connector.

Every request requires an `Idempotency-Key`. The service stores only its SHA-256 hash together with a canonical request hash. Repeating the same actor/key/request replays the original result; reusing the same actor/key for different content fails closed.

Successful authenticated context versions persist publisher provenance separately from semantic `owner` and `source` metadata:

- publisher subject;
- principal kind;
- publisher client ID;
- publication action;
- publication permission.

Bootstrap/seed rows retain null publisher provenance because they belong to the existing administrative trust boundary.

Publication attempts are recorded in an append-only `publication_audit` table. The audit stores identifiers, hashes, authority/action/permission, outcome, and immutable record references, but not the raw context payload.

Supersession preserves key/domain through the existing immutable-version repository and additionally cannot change authority level through this API. Authority transitions are deferred to the PR-026 approval workflow.

## Rationale

The authenticated actor is a security fact; semantic ownership/source is business metadata. Keeping them separate prevents an authorized publisher from impersonating another publisher merely by writing an `owner` field.

Idempotency protects clients from duplicate immutable versions caused by retries.

Preserving authority across direct supersession closes the obvious downgrade/escalation path before the high-authority approval workflow exists.

## Consequences

- user/agent/client identity is never accepted from the write request body;
- publication permission is re-evaluated on each new idempotency key;
- a previously denied request replayed with the same idempotency key remains denied; clients must use a new key after authorization state changes;
- semantic owner/source-reference metadata remains descriptive and must not be treated as publisher identity or an authorization grant;
- API-authored rows are persisted with `source_type=api`; connector source attestation remains future work;
- high-authority policy/mandatory-control writes are permission-gated but do not yet have second-party approval until PR-026;
- PR-027 will extend adversarial coverage for replay, concurrent supersession, forged metadata, and approval bypass.
