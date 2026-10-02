# ADR-017 — Authorize Publication by Explicit Authority Permission

**Status:** Accepted  
**Date:** 2026-10-02

## Context

The MVP read path is governed and authenticated, but the bootstrap/seed path still trusts an operator to assign owner, source, and authority metadata.

Before exposing an authenticated write API, ContextPlane needs a provider-neutral authorization rule for who may assign each authority level. The model must not assume that a high-authority publisher automatically inherits unrelated lower-authority publishing rights, and user self-preferences need a narrow path that cannot be repurposed to target other users.

## Decision

Authenticated publication uses explicit permissions:

- `context.publish.preference.self`
- `context.publish.preference`
- `context.publish.recommendation`
- `context.publish.standard`
- `context.publish.policy`
- `context.publish.mandatory_control`

Permissions may arrive through normalized scopes or roles.

No authority permission implies another authority permission. In particular, `context.publish.mandatory_control` does not automatically grant `context.publish.standard`, and preference rights never imply policy rights.

`context.publish.preference.self` is a special narrow case:

- principal kind must be user;
- target `scope.user_id` must equal the authenticated subject;
- target `scope.agent_id` must be absent;
- it does not authorize unscoped, team-scoped, or another user's preference.

All publication requests must target the authenticated tenant.

The authorization decision returns the authenticated actor identity, action, authority level, and permission used so the future write path can persist an auditable publication event.

## Rationale

Explicit authority permissions preserve least privilege and avoid dangerous implicit hierarchies. A security team may be allowed to publish mandatory controls without also being authorized to publish arbitrary engineering standards, and a normal user can manage only their own preference context without becoming an organizational publisher.

Tenant equality is checked before authority evaluation so a valid publisher in one tenant cannot use the same permission to write another tenant.

## Consequences

- PR-025 can expose authenticated authoring without inventing authorization semantics inside route handlers;
- every authority assignment has an explicit permission requirement;
- future approval workflows can build on the same publication decision;
- operator-controlled YAML seeding remains an administrative/bootstrap path and is not converted into end-user publishing by this ADR;
- actor provenance must be stored separately from semantic `owner` and source metadata when the write API is implemented.
