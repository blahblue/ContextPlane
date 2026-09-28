# Contributing to ContextPlane

ContextPlane is an early technical project. Contributions should optimize for correctness, clarity, testability, and security rather than feature breadth.

## Read first

- [Architecture](docs/ARCHITECTURE.md)
- [Context model](docs/CONTEXT_MODEL.md)
- [Security model](docs/SECURITY.md)
- [Threat model](THREAT_MODEL.md)
- [Verification loop](docs/VERIFICATION.md)

## Engineering principles

- Keep business logic out of protocol adapters.
- Treat imported source content as untrusted.
- Fail closed on authentication and authorization errors.
- Preserve provenance and version history.
- Never treat a model instruction as a security boundary.
- Prefer deterministic policy and resolution behavior.
- Avoid infrastructure the MVP does not yet require.

## Pull requests

Each PR should describe:

1. **Problem**
2. **Invariant**
3. **Design**
4. **Security implications**
5. **Verification plan**
6. **Documentation impact**
7. **Deferred follow-ups**

Use the repository pull-request template.

## Testing

Add tests at the closest useful layer:

- unit tests for resolution and precedence;
- database integration tests;
- API/MCP contract tests;
- identity and tenant-boundary tests;
- adversarial tests for bypass and over-retrieval;
- regression tests for fixed behavior.

## Documentation policy

Technical behavior belongs in this repository. Product strategy, branding, and competitive planning are intentionally kept outside the public codebase.

If a change modifies an invariant, schema, protocol, security boundary, or architectural decision, update the relevant documentation in the same PR.

## Security-sensitive changes

For changes involving authentication, authorization, tenant boundaries, secrets, policy enforcement, or source ingestion, include explicit negative tests.

Never commit real enterprise credentials, tokens, internal documents, customer data, or proprietary source material.

## License

By contributing, you agree that your contributions are licensed under Apache-2.0.
