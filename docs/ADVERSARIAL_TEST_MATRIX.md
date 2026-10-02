# Adversarial Security Regression Matrix

PR-019 turns the threat model into a reusable regression suite.

The goal is not to duplicate every component test. It is to verify that security invariants still hold when identity, policy, resolution, precedence, cache, MCP, audit, and immutable context interact.

## Attack matrix

| ID | Threat | Attack | Expected invariant | Coverage |
|---|---|---|---|---|
| A01 | T1 cross-tenant leakage | Principal A resolves while only tenant B context exists | No tenant B context returned | PR-019 integration |
| A02 | T1/T2 identity scope | User B requests selectors matching user A context | User A context not returned | PR-019 integration |
| A03 | T2 privilege escalation | Principal without `context.resolve` supplies privileged selectors | Runtime rejects before resolution and writes a denied audit record | PR-019 integration |
| A04 | T1/T2 policy injection | Foreign-tenant policy rule enters runtime | Fail closed and audit policy configuration error | PR-019 integration + policy unit |
| A05 | T4 prompt injection | Context payload says “ignore policy / change tenant / return secrets” | Text remains data; metadata authority and tenant remain unchanged | PR-019 integration |
| A06 | T5 poisoning | Narrow user preference conflicts with broader non-overridable standard | Authoritative standard wins | PR-019 unit + integration |
| A07 | T5 poisoning | Preference conflicts with mandatory control | Mandatory control wins | PR-019 unit |
| A08 | T5 governance ambiguity | Equal-authority/equal-scope conflicting values | Fail closed with governance conflict | PR-019 unit + existing runtime tests |
| A09 | T6 stale context | Warm cache exists when authoritative context is superseded | New tenant revision selects version 2 | PR-019 integration |
| A10 | T6 stale policy | Policy effect changes allow -> deny | Policy fingerprint changes cache identity | PR-019 unit |
| A11 | T7 over-retrieval | Narrow rule contains unrequested keys | Policy cannot add unrequested keys | PR-019 unit |
| A12 | T7 redaction bypass | One narrow rule allows a key another redacts | Redaction remains monotonic | PR-019 unit + integration |
| A13 | T9 cache confusion | Tenant changes | Cache key changes | PR-019 unit |
| A14 | T9 cache confusion | Subject changes | Cache key changes | PR-019 unit |
| A15 | T9 cache confusion | Client changes | Cache key changes | PR-019 unit |
| A16 | T9 cache confusion | Roles/groups/scopes change | Cache key changes | PR-019 unit |
| A17 | T9 cache confusion | Repository selector changes | Cache key changes | PR-019 unit |
| A18 | T9 cache confusion | Context revision changes | Cache key changes | PR-019 unit |
| A19 | T12 MCP identity injection | Tool arguments attempt to supply tenant/user/client identity | Authenticated principal remains authoritative | Existing MCP adversarial integration |
| A20 | T13 helper domain injection | Engineering helper receives security-domain-like extra input | Server-fixed helper domain remains engineering | Existing MCP helper integration |
| A21 | T8 forged JWT | Wrong issuer/audience/signature/algorithm/expiry | Authentication fails closed | Existing OIDC/Entra suites |
| A22 | T8/T3 ambiguous identity | Agent/service identity is malformed or ambiguous | Authentication fails closed | Existing OIDC/Entra suites |
| A23 | T10 audit tampering | UPDATE/DELETE audit row | PostgreSQL rejects ordinary mutation | Existing audit integration |
| A24 | T10 audit disclosure | Different actor requests another actor's audit | 404 / no disclosure | Existing audit integration |
| A25 | T14 enforcement illusion | Mandatory context is returned to an LLM | Documentation does not claim model obedience is enforcement | ADR-003 + client-demo reviews |

## What the suite does not prove

This suite does not claim:

- resistance to a database owner or host administrator;
- safety of external connectors that do not yet exist;
- protection from an administrator who is already trusted to publish arbitrary high-authority seed metadata;
- that an LLM will obey returned context;
- authorization to an underlying repository merely because a repository selector matches;
- production robustness of remote JWKS rotation, Graph group-overage expansion, or tenant-specific Copilot configuration.

Those remain separate trust boundaries or future hardening work.

## Regression rule

A future PR that changes identity, policy, resolver scope, cache keying, source ingestion, precedence, MCP adapters, or audit behavior should run this matrix unchanged.

If an invariant intentionally changes, update the threat model, this matrix, and the relevant ADR in the same PR rather than weakening a test silently.
