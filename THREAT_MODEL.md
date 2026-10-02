# Threat Model

Status: draft  
Last updated: 2026-10-02

## Scope

ContextPlane resolves organizational context for AI clients based on identity, task, resource, and policy.

Primary assets:

- organizational context and policy;
- identity and authorization claims;
- provenance and version metadata;
- audit records;
- source-system references;
- integration credentials.

The LLM is **outside** the trusted computing base.

## Trust boundaries

```text
[User / Agent]
      |
      v
[Gateway API / MCP]
      |
      v
[Identity + Policy Boundary]
      |
      v
[Context Resolver]
   /        \
  v          v
[Registry] [Sources]
      |
      v
[Audit]
```

External source content is untrusted even when retrieved from an authenticated enterprise system.

## Threats

### T1 — Cross-tenant leakage

A principal retrieves another tenant's context.

Mitigations:

- tenant required in every principal;
- tenant filtering before candidate selection;
- tenant included in cache keys;
- transaction-local authenticated tenant binding;
- PostgreSQL RLS for non-owner runtime roles;
- fail closed on missing/ambiguous tenant;
- negative integration tests including direct non-owner database access.

### T2 — User privilege escalation

A user requests context outside their authorized scope.

Mitigations:

- validated OIDC claims;
- explicit policy evaluation;
- never trust requested scope as authorization;
- audit denied requests.

### T3 — Agent privilege escalation

An agent has broader access than the user it acts for, or user and agent identity are conflated.

Current mitigations:

- distinct user, agent, and service principals;
- deny ambiguous identity classification;
- authenticated MCP identity cannot be supplied through model tool arguments.

Deferred hardening:

- explicit on-behalf-of identity chains;
- effective authorization derived from both human and delegated agent identity where the provider supplies that relationship.

### T4 — Prompt injection in source content

A document says “ignore policy” or attempts to redefine authority.

Mitigations:

- content never grants authority by wording;
- authority comes from metadata, owner, source, and publication workflow;
- source text is data, not executable policy.

### T5 — Context poisoning

A malicious or low-quality source introduces false context.

Current mitigations:

- explicit source ownership and provenance metadata;
- immutable versions;
- deterministic authority/override precedence;
- equal-precedence conflicts fail closed.

Current trust assumption:

- the YAML seed path is operator-controlled bootstrap input; ContextPlane currently trusts the authority/owner metadata admitted through that administrative boundary.

Current publishing hardening:

- PR-024 defines explicit, non-inheriting publication permissions for every authority level;
- self-preference publication is restricted to the authenticated user and cannot target another user or unscoped organizational context;
- publication tenant and publisher identity are server-derived from the authenticated principal;
- PR-025 persists authenticated publisher provenance separately from semantic owner/source metadata;
- API-authored context is server-labeled `source_type=api`, so callers cannot claim connector attestation;
- publication writes require bounded idempotency keys and immutable supersession;
- direct supersession cannot change authority level before approval workflow support;
- publication attempts are payload-minimized and append-only audited.

Deferred hardening:

- owner/approver workflow for policy and mandatory-control publication;
- external source connector publication authorization and attestation.

### T6 — Stale policy

An old policy remains active after supersession.

Mitigations:

- effective dates;
- version-aware cache invalidation;
- supersession links;
- freshness checks;
- audit exact policy versions used.

### T7 — Over-retrieval

The gateway returns more context than required.

Mitigations:

- task/resource/audience-aware resolution;
- sensitivity filtering;
- minimum-context objective;
- evaluation metric for retrieval size.

### T8 — Forged or invalid JWT

A caller supplies a token with bad issuer, audience, signature, expiry, or tenant.

Mitigations:

- strict OIDC validation;
- explicit allowed issuers/audiences;
- short clock-skew tolerance;
- deny on validation ambiguity.

### T9 — Cache confusion

Cached context is reused across users, tenants, or policy versions.

Mitigations:

- opaque cache keys include tenant, subject, principal kind, client identity, roles, groups, scopes, and resolver scope;
- cache keys include a monotonic tenant context revision and deterministic policy fingerprint;
- PostgreSQL bumps context revision on context-item INSERT, UPDATE, or DELETE;
- cache expiry is bounded by both TTL and the next effective-time transition;
- only candidate resolution is cached; policy, precedence, provenance, and audit remain per-request;
- integration tests verify cross-principal isolation and authoritative-update invalidation.

### T10 — Audit tampering

A privileged actor alters decision history.

Mitigations:

- append-only PostgreSQL audit design;
- database trigger rejects ordinary UPDATE and DELETE operations;
- exact-actor lookup scope;
- payload-minimized audit schema;
- resolution IDs correlate runtime outcomes to stored records;
- publication audit records are also append-only, tenant-RLS scoped, and reject ordinary UPDATE/DELETE.

Future hardening includes external WORM/SIEM sinks and cryptographic log chaining.

### T11 — Secret exposure

Credentials or tokens enter the context graph.

Mitigations:

- store references, not secret values;
- use enterprise secret stores;
- resolution audits omit bearer tokens, raw context payloads, selector values, and source URIs;
- redact sensitive logs.

### T12 — MCP identity injection or transport confusion

**Threat:** A model attempts to select its own tenant/user/agent identity through tool arguments, or an operator assumes stdio/in-process MCP is protected by HTTP bearer authentication.

**Mitigations:**
- identity fields are absent from the `resolve_context` tool schema;
- remote identity is derived only from the verified MCP access-token context;
- extra model-supplied identity-like arguments cannot change the normalized Principal;
- Entra validation is reused rather than reimplemented;
- `context.resolve` permission is required for the remote MCP resource server;
- legacy Streamable HTTP is served statelessly;
- documentation explicitly defines stdio/in-process security as the process boundary.

### T13 — MCP helper domain or selector confusion

**Threat:** A model attempts to widen a domain-specific helper by injecting another domain, or an operator treats a model-supplied repository/resource selector as proof of authorization.

**Mitigations:**
- helper domain sets are fixed in server code and absent from helper tool schemas;
- every helper delegates to the shared authenticated/policy-governed runtime;
- identity remains outside helper arguments;
- repository/resource are documented as applicability selectors only;
- sensitive underlying resource access must be enforced by policy or a downstream resource boundary;
- integration tests verify helper domain pinning and repository-scope matching.

### T15 — Publication replay, spoofing, or authority transition

**Threat:** An authenticated publisher retries a write into duplicate immutable versions, injects tenant/publisher identity, spoofs connector provenance, reuses an idempotency key with different content, or attempts to downgrade/upgrade authority through supersession.

**Mitigations:**
- tenant and authenticated publisher provenance are server-derived;
- external write schemas reject tenant/publisher/checksum fields;
- each authority assignment uses PR-024 explicit permissions;
- API source type is server-fixed;
- Idempotency-Key is required and stored only as a hash alongside a canonical request hash;
- same-key/different-request replay fails closed;
- direct supersession preserves authority level;
- context versions and publication audit history are immutable;
- publication audit is tenant-RLS scoped.

**Deferred:** PR-026 adds second-party approval state for policy/mandatory-control writes; PR-027 adds concurrent replay and approval-bypass adversarial cases.

### T14 — Mandatory-context illusion

Users assume a “mandatory” instruction guarantees downstream model compliance.

Mitigations:

- explicitly distinguish advisory context from enforced authorization;
- protect sensitive resources at an enforceable boundary;
- never market prompt obedience as security.

## Security test categories

PR-019 adds a cross-component adversarial regression matrix in [docs/ADVERSARIAL_TEST_MATRIX.md](docs/ADVERSARIAL_TEST_MATRIX.md).

The MVP includes tests for:

- cross-tenant denial;
- user privilege escalation;
- agent privilege escalation;
- invalid token variants;
- prompt-injection content;
- stale/superseded policies;
- cache-key isolation;
- context-revision invalidation;
- policy-fingerprint invalidation;
- effective-time cache expiry;
- over-retrieval;
- context poisoning;
- mandatory-control override attempts;
- MCP identity-like argument injection;
- MCP token without context.resolve permission;
- MCP invalid bearer token;
- MCP helper domain-injection attempts;
- repository/resource selector applicability without treating selectors as identity;
- audit update/delete attempts;
- cross-actor audit lookup;
- audit payload minimization.
