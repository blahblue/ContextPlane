# ADR-001 — MCP Is an Interface, Not the Product

**Status:** Accepted  
**Date:** 2026-09-28

## Context

Managed MCP gateways already exist across major cloud, data, and agent platforms. A generic MCP proxy is not sufficient differentiation.

## Decision

The core system will be a protocol-independent context resolver with MCP, REST, and SDK interfaces.

## Rationale

The distinctive capability is identity-aware resolution of authoritative organizational context and policy, not transport.

## Consequences

- Business logic must not live inside MCP handlers.
- MCP tools call the same resolver used by REST/SDK clients.
- Protocol changes must not require redesigning the context graph or policy engine.
