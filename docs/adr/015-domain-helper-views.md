# ADR-015 — Treat Domain MCP Helpers as Constrained Views over the Shared Runtime

**Status:** Accepted  
**Date:** 2026-10-01

## Context

The generic MCP `resolve_context` tool can resolve any supported context domain, but common clients repeatedly need narrower semantic capabilities such as engineering standards, brand/presentation guidance, or security/policy context.

Implementing those capabilities as separate retrieval paths would duplicate policy, identity, cache, precedence, provenance, and audit behavior. Allowing the model to choose the helper's domain would also make the helper only cosmetic.

ContextPlane already models repository and resource as applicability dimensions in `ContextScope`, but the transport-neutral runtime did not yet expose them.

## Decision

Domain-specific MCP helpers are constrained views over `resolve_context_runtime`.

The initial helpers are:

- `get_engineering_context` -> engineering;
- `get_brand_presentation_context` -> brand + presentation;
- `get_policy_context` -> security context, including security policy and mandatory-control context represented in the context registry.

The domain set is fixed in server code and is not part of each helper's tool schema.

All helpers use the same authenticated Principal and shared runtime as the generic MCP tool. They do not implement separate authorization, policy evaluation, resolution, precedence, cache, provenance, or audit behavior.

Repository and resource are added to the transport-neutral request as **applicability selectors** and map to the existing `ContextScope` fields.

They are not identity and do not grant access by themselves.

## Rationale

Semantic helper tools make agent behavior easier to reason about while preserving one governed execution path.

Server-fixed domains make each helper materially narrower than generic search or resolution.

Keeping repository/resource as selectors enables repository-specific engineering context without pretending that a model-provided repository name is an authorization credential.

## Consequences

- every helper invocation receives the same policy and audit treatment as generic resolution;
- helper domain behavior can be tested independently of model prompting;
- a caller cannot change an engineering helper into a security-domain helper through tool arguments;
- clients may use repository/resource to select applicable context, but sensitive resource authorization must be enforced separately by policy/resource boundaries;
- future helper tools must compose the shared runtime instead of querying context tables directly;
- PR-017 can build a coding-agent demo on the engineering helper without adding a second resolver.
