# ADR-009 — Normalize Provider Tokens into Distinct ContextPlane Principals

**Status:** Accepted  
**Date:** 2026-09-28

## Context

ContextPlane will integrate with multiple enterprise identity providers and agent runtimes. Provider-specific claims differ, but policy and context-resolution layers need a stable internal identity contract.

Human users, autonomous agents, and service applications must not be collapsed into one subject type. Doing so makes delegation and authorization boundaries ambiguous.

## Decision

ContextPlane defines a provider-neutral `Principal` with:

- tenant ID;
- subject ID;
- principal kind: `user`, `agent`, or `service`;
- optional client/application ID for users;
- required client/application ID for agents and services;
- normalized roles, groups, and scopes.

Identity-provider adapters implement the `PrincipalValidator` protocol and return this normalized model only after cryptographic token validation.

The first reference validator uses a pinned public key and accepts only RS256 tokens for a configured issuer and audience. It requires standard expiry/issued-at/issuer/audience/subject claims and then validates ContextPlane identity claims.

Provider-specific claim inference is deferred to provider adapters. The generic validator does not guess whether a subject is a human, agent, or service.

## Rationale

A normalized principal keeps policy and resolver code independent from Entra, Okta, or another provider while preserving the identity distinctions required for later on-behalf-of and agent authorization semantics.

## Consequences

- Entra integration maps Entra-specific claims into this principal rather than leaking Entra claim names into core policy code;
- invalid or ambiguous identity claims fail closed;
- agents/services require a separate client identity;
- signing-key discovery and rotation are adapter concerns;
- new identity providers can implement the same validator boundary.
