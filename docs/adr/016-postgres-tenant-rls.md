# ADR-016 — Use PostgreSQL RLS as Tenant Defense in Depth

**Status:** Accepted  
**Date:** 2026-10-02

## Context

ContextPlane already scopes runtime queries by the authenticated tenant and has adversarial cross-tenant tests. A programming mistake in a future query could still omit that predicate.

PostgreSQL row-level security can reduce that blast radius, but only when the application connects as a role that is actually subject to RLS. Table owners and superusers bypass ordinary RLS policies unless FORCE ROW LEVEL SECURITY is used, and migration/bootstrap workflows need deliberate administrative access.

## Decision

Tenant-bearing runtime tables use PostgreSQL RLS policies keyed by a transaction-local setting:

`contextplane.tenant_id`

The shared runtime binds this setting from the already authenticated ContextPlane Principal before any tenant-bearing database read or audit write. Audit lookup binds the tenant before querying as well.

The policies cover:

- `context_items`;
- `context_relations`;
- `context_state_revisions`;
- `resolution_audit`.

The application continues to include explicit tenant predicates. RLS is defense in depth, not a replacement for application authorization.

The migration enables RLS but does **not** use FORCE ROW LEVEL SECURITY and does not create a production role. Deployment operators must use:

- an owner/migration role for migrations/bootstrap;
- a separate non-owner runtime role with only the table privileges required by the running service.

The current seed/bootstrap path is therefore an administrative path rather than an end-user publishing API.

Production database transport protection is separately enforceable with `CONTEXTPLANE_DATABASE_REQUIRE_TLS=true`. When enabled, ContextPlane refuses database URLs without `sslmode=require`, `verify-ca`, or `verify-full`. Production deployments should prefer `verify-full` when certificate infrastructure permits it.

## Rationale

This creates an independent database-level tenant boundary without pretending that a table owner is protected by ordinary RLS or breaking administrative migration workflows.

Using `set_config(..., true)` keeps the tenant binding transaction-local and parameterized.

## Consequences

- runtime deployments that rely on RLS must not connect as a table owner or superuser;
- missing tenant session state yields no rows for non-owner runtime roles;
- cross-tenant inserts are rejected by WITH CHECK;
- explicit application tenant filters remain mandatory;
- migrations and seed/bootstrap operations retain a separate administrative trust boundary;
- production TLS can be required through application configuration without breaking local PostgreSQL development.
