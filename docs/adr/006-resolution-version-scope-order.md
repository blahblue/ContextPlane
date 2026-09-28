# ADR-006 — Resolve Version Applicability Before Scope Specificity

**Status:** Accepted  
**Date:** 2026-09-28

## Context

Each logical context item can have multiple immutable versions with effective windows and different scopes. If scope filtering is applied before version selection, an older broad version can incorrectly reappear when a newer active version has a narrower scope.

A second failure mode occurs when an expired newer version is filtered out before lineage selection: an older predecessor with no explicit end date can reactivate after the successor expires.

Both behaviors are unsafe for governed context.

## Decision

For each tenant and logical context identity, candidate resolution will:

1. ignore versions whose `effective_from` is in the future;
2. select the highest version whose effective start has been reached;
3. discard that selected version if its `effective_to` has passed;
4. only then evaluate scope matching.

A predecessor never reactivates after a newer version has taken effect.

For scope matching, a null context-item dimension is a wildcard. A non-null context-item dimension requires an equal value in the resolution request. Missing request dimensions do not satisfy explicit item scope.

An explicit empty domain filter means “return no domains,” not “disable filtering.”

## Rationale

This produces conservative, deterministic behavior and prevents broad or retired context from being resurrected by version or filter edge cases.

## Consequences

- scheduled future versions do not hide the current version before their effective start;
- expired latest-started versions retire the logical item until a later version becomes effective;
- scope changes in a newer version cannot cause an older version to reappear;
- conflict precedence remains separate and is applied only after candidate resolution.
