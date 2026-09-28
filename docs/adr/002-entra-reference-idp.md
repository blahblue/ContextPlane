# ADR-002 — Microsoft Entra Is the Reference Identity Provider

**Status:** Accepted for MVP  
**Date:** 2026-09-28

## Context

The MVP needs a realistic enterprise identity provider while avoiding a custom IAM subsystem.

## Decision

Use OIDC as the identity abstraction and Microsoft Entra as the first enterprise reference integration.

## Rationale

Entra is broadly deployed in enterprises and supports rich user, application, and agent identity scenarios.

## Consequences

- Core authorization logic cannot depend directly on Entra-specific claims.
- An adapter maps provider claims into the internal principal model.
- Local development uses a test issuer so contributors do not need an Azure tenant.
