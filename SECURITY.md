# Security Policy

ContextPlane is security-sensitive infrastructure because it may sit between enterprise identities, organizational context, AI agents, and protected resources.

## Supported versions

The project is pre-1.0. Security fixes are applied to the current `main` branch. A formal supported-version policy will be introduced when tagged releases begin.

## Reporting a vulnerability

Do **not** open a public issue for vulnerabilities that could expose credentials, tenant data, authorization bypasses, or exploit details.

Preferred process:

1. Use GitHub private vulnerability reporting / security advisories if enabled.
2. If unavailable, contact the maintainer privately through GitHub before publishing technical details.
3. Include reproduction steps, affected components, expected impact, and suggested mitigation if known.

Do not include real credentials, production tokens, customer data, or proprietary enterprise content in reports.

## High-priority classes

- authentication bypass;
- authorization bypass;
- cross-tenant data access;
- user/agent identity confusion;
- incorrectly validated JWTs;
- context exfiltration;
- mandatory-policy bypass;
- prompt injection becoming authoritative policy;
- provenance spoofing;
- context poisoning;
- insecure secret handling;
- audit-log tampering;
- unsafe defaults.

## Security principles

- Fail closed.
- Keep user and agent identities distinct.
- Minimize returned context.
- Treat source content as untrusted input.
- Grant authority through explicit metadata and workflow, never document wording.
- Preserve immutable versions and provenance.
- Do not rely on LLM compliance as a security control.
- Store secrets in dedicated secret-management systems, not the context graph.

See [THREAT_MODEL.md](THREAT_MODEL.md) and [docs/SECURITY.md](docs/SECURITY.md).
