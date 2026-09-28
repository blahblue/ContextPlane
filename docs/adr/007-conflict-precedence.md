# ADR-007 — Resolve Context Conflicts with Authority, Specificity, and Explicit Override

**Status:** Accepted  
**Date:** 2026-09-28

## Context

After candidate resolution, multiple applicable logical context items can share the same key. ContextPlane must produce one effective value without making implicit or unstable choices.

Authority and scope specificity are not interchangeable. A narrower item may represent legitimate local customization, but a broader governing item may explicitly forbid override. Mandatory controls require stronger semantics than ordinary preferences or standards.

## Decision

Conflict resolution operates per context key.

Authority order is:

```text
preference < recommendation < standard < policy < mandatory_control
```

Rules:

1. At equal scope specificity, higher authority wins.
2. At greater scope specificity:
   - a mandatory control cannot be overridden by lower-authority context;
   - a narrower mandatory control overrides lower-authority broader context;
   - higher-authority narrower context wins;
   - otherwise, narrower context wins only when the current broader winner has `override_policy=allow`.
3. Equal-authority, equal-specificity candidates with different semantics fail closed.
4. Equal-authority, equal-specificity candidates are deduplicated only when payload, domain, sensitivity, override policy, and matched scope dimensions are equivalent.
5. Every pairwise suppression is recorded as an attributable decision step.

## Rationale

This keeps governance explicit while still allowing scoped customization where an authoritative context item permits it. Failing closed on unresolved exact-precedence conflicts is safer than selecting by insertion order, UUID, or source accident.

## Consequences

- personal/team overrides can be enabled intentionally;
- broad deny semantics remain authoritative unless a narrower item carries higher authority;
- mandatory controls cannot be displaced by lower-authority customization;
- ambiguous same-rank conflicts must be corrected in source governance;
- future source-authority ranking would require a separate ADR rather than silently changing tie behavior.
