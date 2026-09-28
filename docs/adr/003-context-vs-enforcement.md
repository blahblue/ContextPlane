# ADR-003 — Separate Mandatory Context from Hard Enforcement

**Status:** Accepted  
**Date:** 2026-09-28

## Context

An LLM may ignore a textual instruction even when the gateway labels it mandatory.

## Decision

The architecture explicitly distinguishes mandatory context returned to an AI client from security controls enforced at a resource or authorization boundary.

## Rationale

Context correctness and security enforcement are different guarantees.

## Consequences

- Documentation must never imply prompt instructions are security boundaries.
- Security-sensitive demos should include resource-enforced paths when possible.
- Tests separately verify context correctness and authorization enforcement.
