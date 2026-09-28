# ADR-008 — Separate Domain Admission from Monotonic Key Narrowing

**Status:** Accepted  
**Date:** 2026-09-28

## Context

ContextPlane needs policy semantics that can deny context domains, allow higher-authority exceptions, and reduce the amount of context returned without accidentally broadening a request.

Admission and redaction have different safety properties. An explicit higher-authority allow may legitimately override a lower-authority domain deny. By contrast, silently removing a key redaction because another rule says “allow” can expose context unexpectedly.

## Decision

The MVP policy evaluator separates:

1. **Domain admission** — `allow` and `deny` rules.
2. **Key narrowing** — `narrow` rules containing allowlists and/or redactions.

Executable rules must carry either `policy` or `mandatory_control` authority.

For each requested domain:

- only rules targeting that domain participate;
- the highest applicable authority level controls admission;
- `deny` wins an allow/deny tie at the same authority;
- mandatory-control admission rules outrank policy admission rules;
- absence of an admission rule defaults to allow inside the already authenticated/authorized tenant boundary.

Narrowing is monotonic in the MVP:

- key allowlists intersect;
- redaction sets union;
- an allow rule does not erase narrowing;
- narrowing never adds domains or keys that were not requested;
- if every requested domain is denied, known requested keys are returned as an empty allowed set.

Cross-tenant policy input aborts evaluation.

## Rationale

Separating admission from narrowing avoids ambiguous “allow” semantics and makes accidental data expansion harder. The monotonic model is intentionally conservative until ContextPlane has an explicit, audited exception mechanism.

## Consequences

- policy evaluation does not replace authentication or tenant authorization;
- mandatory allow can override a lower-authority domain deny, but does not automatically remove redactions;
- future redaction exceptions require an explicit design/ADR;
- identity-aware conditions can be added later without changing the core decision semantics;
- policy rules cannot broaden the original request.
