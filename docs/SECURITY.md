# Security Architecture

## Objective

No AI client receives context merely because it can reach the gateway. Every request must be evaluated against authenticated user and/or agent identity plus explicit policy.

## Principal model

Represent separately:

- tenant;
- human user;
- agent/service identity;
- acting-on-behalf-of relationship, when available;
- groups/roles;
- application/client identity.

Do not collapse user and agent into one principal.

## Authentication boundary

Identity-provider adapters validate bearer tokens and normalize them into a provider-neutral principal. Core code preserves separate human-user, agent, and service identities.

The reference generic OIDC validator:

- pins the accepted algorithm to RS256;
- validates signature, issuer, audience, expiry, issued-at, and subject;
- requires a non-empty tenant;
- requires explicit principal type;
- requires a client/application ID for agents and services;
- normalizes roles, groups, and scopes;
- returns a generic authentication failure rather than exposing validation internals.

Remote signing-key discovery and provider-specific claim mapping are adapter responsibilities.

## Authorization inputs

A policy decision may consider:

- subject user;
- actor agent;
- application;
- tenant;
- groups;
- roles;
- requested domains;
- task;
- audience;
- resource;
- environment.

## Strong vs. weak controls

Weak controls:

- system prompts;
- client instructions;
- “always call this tool first.”

These improve behavior but are not security boundaries.

Strong controls:

- token validation;
- RBAC/ABAC;
- gateway-enforced filtering;
- resource access mediated by policy;
- short-lived scoped credentials.

## Policy evaluation

The policy layer distinguishes domain admission from key narrowing.

- Allow/deny rules are resolved at the highest applicable authority.
- Deny wins ties at equal authority.
- Mandatory-control admission rules outrank ordinary policy rules.
- Narrowing is monotonic: allowlists intersect and redactions union.
- Policy evaluation never adds an unrequested domain or key.
- Cross-tenant policy inputs fail closed.

Default allow in this layer does **not** mean unauthenticated access. Policy evaluation is designed to operate inside the authenticated tenant boundary described below.

See ADR-008 for the exact semantics.

## Entra reference path

The reference Entra adapter keeps Microsoft-specific claims outside core policy and resolver code.

For the current MVP:

1. register ContextPlane as a protected API;
2. accept an access token issued for the configured tenant and audience;
3. validate signature, issuer, audience, expiry/issued-at, and tenant;
4. map immutable `tid + oid` into the normalized principal;
5. preserve the calling application through `azp` or `appid`;
6. map delegated `scp`, application/user `roles`, and complete `groups` claims;
7. distinguish user, service, and Entra Agent ID principals;
8. fail closed on group-overage claims until Microsoft Graph membership expansion exists.

Mutable claims such as email, UPN, display name, and preferred username must not be used as authorization identity.

The current reference validator pins an RSA public key for deterministic local testing. Production-style JWKS discovery/rotation and Conditional Access claims-challenge handling are intentionally deferred.

See ADR-010 for the mapping semantics.


## Runtime resolve boundary

The public `POST /v1/context/resolve` contract derives tenant, user/agent subject, and application identity from the validated principal. The request body cannot supply those fields.

Task, audience, and environment are contextual selectors, not authorization credentials. Repository/resource/team/role/business-unit selectors remain outside the public contract until they can be bound to an entitlement decision.

Authenticated principals that lack `context.resolve` are rejected before policy/context retrieval and the denial is written to the resolution audit with no context payload. Policy is then evaluated before context retrieval. Domain denial can short-circuit retrieval, and key narrowing is applied before conflict precedence.

Runtime provenance intentionally omits raw source URIs. The API returns enough provenance to identify owner/source/version while avoiding unnecessary disclosure of internal source locations.

See ADR-011 for the transport-boundary decision.

## Resolution audit boundary

Handled authenticated resolve outcomes are assigned a unique resolution ID and persisted before the runtime response is finalized.

The audit record is intentionally payload-minimized. It stores decision metadata and immutable context-version references, but not bearer tokens, raw context values, prompt text, source URIs, policy bodies, or task/audience/environment values.

PostgreSQL rejects ordinary UPDATE and DELETE operations on resolution audit rows. The initial lookup endpoint is further restricted to the exact tenant, subject, principal kind, and client identity that created the record; mismatches return 404.

Audit rows still contain enterprise identifiers and must be treated as sensitive operational data. The database trigger is not a claim of tamper-proof storage against a database owner. External WORM/SIEM sinks and retention policy are deferred.

See ADR-012 for the audit-storage decision.

## Cache isolation boundary

Candidate-resolution caching is scoped by an opaque digest over authenticated principal state, resolver scope, tenant context revision, and configured policy fingerprint.

The key includes tenant, subject, principal kind, client identity, roles, groups, and scopes, so the reference cache does not intentionally reuse candidate results across authorization-relevant identities.

PostgreSQL maintains a monotonic tenant context revision and bumps it on every context-item INSERT, UPDATE, or DELETE. This makes authoritative data mutation select a new cache key without relying on process-local invalidation events.

Because context applicability can change solely with time, each entry also expires no later than the tenant's next known effective-time boundary.

Only candidate selection is cached. Policy evaluation, precedence, provenance loading, and audit creation remain per-request operations.

Cache values contain resolved organizational context in process memory and therefore remain sensitive runtime data. The current reference cache is bounded and process-local. See ADR-013 for the complete boundary.

## MCP authentication boundary

The remote MCP server is an OAuth resource server. Bearer authentication runs before the `resolve_context` tool.

ContextPlane reuses its Entra validator to verify token signature, issuer, API audience, time validity, tenant, and principal mapping. The MCP adapter additionally requires `context.resolve` as either a delegated scope or application role.

Identity is not part of the MCP tool schema. The model can provide domains/keys/task/audience/environment, but tenant, subject, principal kind, client ID, groups, roles, and scopes come only from the verified access-token context.

The reference CLI serves Streamable HTTP with stateless legacy transport behavior. Modern MCP 2026-07-28 requests are already sessionless. This avoids treating a long-lived legacy MCP session as the identity boundary.

MCP bearer authentication does not protect stdio or in-process transports. For those transports, the launcher/embedding process is the trust boundary.

Domain-specific MCP helpers fix their domains in server code and do not expose domain selection to the model. Repository/resource arguments are applicability selectors only; they must never be interpreted as proof that a principal is authorized to access the underlying repository/resource.

See ADR-014, ADR-015, and [MCP.md](MCP.md).

## Prompt injection rule

Source text is untrusted content even when the source system is trusted.

Imported text does not become policy merely because it contains imperative language. Authority is granted only through explicit ownership, metadata, and publication workflow.

## Secrets

Store references to secrets, not secret values. Use enterprise secret-management infrastructure for credentials.

See [../THREAT_MODEL.md](../THREAT_MODEL.md) for adversarial cases.


## HTTP perimeter

The reference FastAPI service adds a bounded process-local fixed-window limiter to `/v1/*` routes before authentication dependencies run. The limiter keys on the direct network peer rather than trusting `X-Forwarded-For` supplied by an arbitrary client.

This is a reference safeguard, not a distributed production abuse-control system. Multi-instance deployments must also enforce rate limits at a trusted ingress/API gateway, with proxy trust configured explicitly.

The REST perimeter also:

- disables Swagger/ReDoc/OpenAPI endpoints by default;
- marks `/v1/*` responses `Cache-Control: no-store, private`;
- emits `X-Content-Type-Options: nosniff`;
- denies framing;
- uses a no-referrer policy;
- disables camera/microphone/geolocation through Permissions Policy;
- applies a restrictive API Content Security Policy;
- emits HSTS when the request is actually observed as HTTPS.

Set `CONTEXTPLANE_EXPOSE_API_DOCS=true` only for a deliberately exposed development/documentation deployment.

The default local limiter is 120 requests/minute per direct peer and is configurable with:

- `CONTEXTPLANE_HTTP_RATE_LIMIT_PER_MINUTE`;
- `CONTEXTPLANE_HTTP_RATE_LIMIT_MAX_CLIENTS`.

Production TLS must still be terminated/enforced at a trusted ingress or at the application server. Do not trust arbitrary forwarded-protocol/client-IP headers merely to make HTTPS or rate-limit checks pass.


## PostgreSQL tenant defense in depth

ContextPlane enables row-level security on its tenant-bearing runtime tables. The policies compare each row's `tenant_id` to a transaction-local `contextplane.tenant_id` setting.

The governed runtime sets that value from the authenticated principal before tenant-bearing database work. Audit lookup does the same.

Application-level tenant predicates remain required. RLS is a second boundary intended to reduce the impact of a future missing tenant predicate.

### Runtime-role requirement

Ordinary PostgreSQL RLS does not constrain table owners or superusers. A production deployment that relies on these policies must therefore separate:

- **migration/admin role** — owns schema and runs migrations/bootstrap;
- **runtime role** — non-owner, non-superuser, granted only the table operations required by the service.

The migration intentionally does not create environment-specific database roles and does not use `FORCE ROW LEVEL SECURITY`, because administrative migration/bootstrap paths must remain explicit rather than being accidentally coupled to runtime tenant state.

CI verifies the policies using a temporary non-owner role: a role bound to tenant A cannot see tenant B rows and cannot insert a tenant B state row.

See ADR-016.

## PostgreSQL transport security

Set:

```text
CONTEXTPLANE_DATABASE_REQUIRE_TLS=true
```

for production deployments. When enabled, application startup rejects a database URL unless it explicitly uses one of:

- `sslmode=require`;
- `sslmode=verify-ca`;
- `sslmode=verify-full`.

Prefer `verify-full` when possible because it verifies both the certificate chain and hostname. Local Docker development may keep TLS enforcement disabled.
