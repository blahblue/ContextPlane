# Security Review — 2026-10-02

Scope: `main` after the completed PR-001 → PR-020 MVP.

Sources used for this review:

- the Outpost Security Validation Checklist, adapted to ContextPlane rather than copied literally;
- the supplied launch-security checklist covering secrets, RLS, server-side auth, rate limiting, validation, response minimization, security headers, HTTPS, and dependency scanning;
- the supplied legal/privacy/accessibility checklist;
- the supplied performance checklist.

## Executive result

No Critical authentication bypass, known cross-tenant disclosure, SQL injection path, committed production credential, or audit-authorization bypass was identified in the reviewed MVP code.

The review did identify several concrete hardening gaps that should be fixed before treating the reference service as production-ready.

| ID | Severity | Finding | Current protection | Action |
|---|---|---|---|---|
| S01 | High | No dependency-vulnerability scan in CI; first scan found PYSEC-2026-1845 in pytest 8.4.2 | pip-audit now blocks CI; pytest upgraded past affected versions | PR-021 remediated |
| S02 | High | No automated repository/history secret scan | full-history Gitleaks now blocks CI | PR-021 remediated |
| S03 | Medium | GitHub Actions used mutable major-version tags | workflow actions pinned to immutable SHAs | PR-021 remediated |
| S04 | Medium | No automated dependency-update configuration | Dependabot now covers pip and GitHub Actions | PR-021 remediated |
| S05 | High | No application/edge rate-limit guarantee for token validation and resolve/audit routes | bounded pre-auth process limiter added; distributed ingress control remains deployment follow-up | PR-022 partially remediated |
| S06 | Medium | No explicit security-header/non-cacheable-response middleware | security headers + no-store/private policy added | PR-022 remediated |
| S07 | Medium | Request key collections were not count-bounded | keys capped at 100; domains capped to supported set | PR-022 remediated |
| S08 | Medium | FastAPI docs/OpenAPI were exposed by default | docs/schema disabled by default with explicit opt-in | PR-022 remediated |
| S09 | High defense-in-depth | PostgreSQL tenant tables relied on application query scoping rather than RLS | explicit tenant filters remain; PR-023 adds RLS for non-owner runtime roles + direct DB isolation tests | PR-023 remediated |
| S10 | Medium | Production database TLS was not enforceable by configuration | PR-023 adds DATABASE_REQUIRE_TLS and sslmode validation | PR-023 remediated |
| S11 | Medium | Production backup/restore and external audit retention are documented as expectations, not executable runbooks | immutable in-DB audit trigger | follow-up ops runbook |
| S12 | Medium | Production Entra uses a pinned public key with remote JWKS rotation deferred | strict issuer/audience/signature/time validation | follow-up identity hardening |
| S13 | Medium supply-chain | No deployable dependency lock/hashes | bounded dependency version ranges | follow-up reproducible-build PR |

## Controls already strong

### Authentication

PASS.

REST uses server-side HTTP Bearer validation. MCP remote transport reuses the Entra validator. JWT validation pins RS256 and checks issuer, audience, signature, time validity, tenant, subject, and client identity. Ambiguous principal types and group overage fail closed.

### Authorization and object/tenant isolation

PASS for the implemented runtime, with database RLS recommended as defense in depth.

Tenant, user/agent subject, and client identity are derived from the authenticated principal. Request bodies cannot supply those fields. Audit lookup is scoped to exact actor identity. The adversarial suite covers cross-tenant, cross-user, cache-confusion, policy-injection, and MCP identity/domain injection attempts.

### SQL/injection

PASS.

Application persistence uses SQLAlchemy expressions and fixed SQL text for migration/health primitives. No user-controlled string concatenation into SQL was identified. Pydantic models use `extra="forbid"` broadly and constrain selector strings.

### Cache leakage

PASS.

Resolution cache keys include tenant, subject, principal kind, client, roles, groups, scopes, resolver scope, tenant context revision, and policy fingerprint. Effective-time expiry is bounded.

### API response minimization

PASS.

Runtime provenance omits raw source URI. Audit storage omits bearer token, raw context payload, prompt/selector values, and source URI. Audit lookup does not expose subject/client identifiers in the public response.

### Health endpoint

PASS.

`/health` returns only a minimal deterministic status.

### Container/database exposure

PASS for local reference configuration.

The application container runs as a non-root user. Compose does not publish PostgreSQL to the host. Production network controls remain deployment responsibility.

## Image-checklist applicability

### Legal/privacy/accessibility

Most consumer-app items are not applicable to the current backend-only repository: cookies, cookie banner, refunds, hidden fees, fake reviews, marketing unsubscribe, child account consent, browser accessibility, and UI asset licensing.

Before a hosted public product is launched, the operator still needs accurate privacy/terms disclosures, processor inventory, retention/deletion handling, and business details appropriate to the target jurisdiction.

### Performance

Already present: SQLAlchemy pooling, database indexes on core tenant lookups, server-side candidate caching, and a reproducible latency benchmark.

Not yet established: load-balanced production deployment, large-corpus query-count/N+1 profiling, explicit request/result cardinality limits, and production load testing. Frontend/CDN/image/browser optimization items are N/A to the current service.

## PR plan

### PR-021 — security baseline and software supply chain

The first enforced pip-audit run immediately found PYSEC-2026-1845 in the prior pytest 8.4.2 development dependency. PR-021 upgrades the test dependency to pytest >=9.0.3 and keeps the audit as a blocking CI gate.

- adopt the ContextPlane-specific security checklist;
- add secret scanning;
- add dependency vulnerability scanning;
- pin CI actions by commit;
- add Dependabot for Python and GitHub Actions;
- extend the PR template with the security review block.

### PR-022 — HTTP/API perimeter and abuse controls

- security headers and private-response cache policy;
- production API-doc exposure setting;
- request-cardinality limits;
- bounded application-level request throttling as a reference safeguard;
- tests for 429 behavior, safe headers, and input limits;
- deployment note that distributed/edge throttling remains required for multi-instance production.

### PR-023 — PostgreSQL tenant defense in depth

- bind authenticated tenant identity into the transaction;
- enable/test RLS on tenant-bearing runtime tables where safe;
- preserve system/bootstrap/migration paths deliberately rather than silently bypassing policy;
- production database TLS configuration and documentation;
- cross-tenant direct-query adversarial tests.

## Residual follow-ups after PR-023

- remote Entra JWKS discovery/rotation and Conditional Access claims challenges;
- dependency lock/hash strategy for deployable releases;
- backup/restore drill and external WORM/SIEM audit export;
- authenticated high-authority publishing workflow;
- production load/resilience testing.

These are explicit follow-ups, not claims of current coverage.
