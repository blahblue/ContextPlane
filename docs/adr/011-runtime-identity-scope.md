# ADR-011 — Derive Runtime Identity Scope from the Authenticated Principal

**Status:** Accepted  
**Date:** 2026-09-28

## Context

The resolver supports many scope dimensions, including tenant, user, agent, application, repository, resource, task, audience, and environment.

A public API must not let callers assert identity dimensions in the request body. Doing so would allow an authenticated caller to ask ContextPlane to resolve context as another tenant, user, or agent.

Some non-identity dimensions can also become authorization-sensitive. Repository and resource selectors, for example, should not be accepted until ContextPlane can prove the principal is authorized for the referenced resource.

## Decision

The runtime resolve API derives these dimensions exclusively from the authenticated principal:

- tenant ID;
- user ID for user principals;
- agent ID for agent principals;
- application/client ID when present.

The initial public request may provide only contextual selectors that are not treated as identity or resource authorization:

- task;
- audience;
- environment.

Repository, resource, team, role, business-unit, tenant, user, and agent selectors are not accepted by the initial public request contract.

Policy evaluation occurs before database resolution and can only narrow the requested domains/keys. An all-domain denial short-circuits retrieval.

## Rationale

The resolver's internal flexibility should not become a privilege-escalation surface at the HTTP boundary.

Deferring repository/resource selectors is safer than treating arbitrary caller input as proof of resource authorization. Those selectors can be introduced once they are bound to an entitlement or resource-policy decision.

## Consequences

- request-body identity injection is structurally impossible under the current schema;
- user/agent/application-scoped context can still resolve automatically;
- team/role/repository/resource scoped context is not yet reachable through the public HTTP API unless a later trusted mapping supplies those dimensions;
- coding-agent and resource-specific integrations must add an authorization-backed selector mechanism rather than simply exposing raw resolver fields;
- internal resolver APIs remain more expressive than the public transport contract.
