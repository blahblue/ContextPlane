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

## Entra reference path

For the MVP:

1. register ContextPlane as a protected API;
2. accept Entra-issued tokens;
3. validate issuer, audience, signature, expiry, tenant, scopes/roles;
4. resolve groups/roles only when needed;
5. represent agent identity separately where available;
6. audit user, agent, application, decision, returned context IDs, and policy versions.

## Prompt injection rule

Source text is untrusted content even when the source system is trusted.

Imported text does not become policy merely because it contains imperative language. Authority is granted only through explicit ownership, metadata, and publication workflow.

## Secrets

Store references to secrets, not secret values. Use enterprise secret-management infrastructure for credentials.

See [../THREAT_MODEL.md](../THREAT_MODEL.md) for adversarial cases.
