# ContextPlane

**ContextPlane is a vendor-neutral runtime for resolving governed organizational context for AI agents.**

Enterprise AI tools often need the same brand, engineering, security, presentation, and operating conventions, but those rules are usually duplicated across prompts, RAG indexes, agent builders, and vendor-specific configuration.

ContextPlane explores a different model: maintain authoritative organizational context once, then resolve the minimum applicable context at runtime based on the **user, agent, task, audience, resource, and policy**.

> Status: early technical exploration. Interfaces and architecture are expected to evolve.

## Core idea

```text
Authoritative Sources
        |
        v
Context Registry + Graph
        |
        +---- Policy Engine
        +---- Identity Resolver
        |
        v
   Context Resolver
        |
   +----+----+
   |         |
  MCP       REST
   |         |
AI clients / agents
```

ContextPlane is **not** intended to be another generic MCP proxy or enterprise search engine. MCP is one interface. The core technical problem is deterministic, explainable, identity-aware context resolution.

## MVP

The initial implementation focuses on four context domains:

- Brand
- Presentation
- Engineering
- Security

The first proof should work across:

- an MCP-capable coding client
- Microsoft Copilot Studio or an equivalent enterprise agent flow
- OIDC authentication, with Microsoft Entra as the reference identity provider

## Design principles

1. Context is infrastructure, not prompt text.
2. Policy outranks preference.
3. Identity is part of context resolution.
4. Retrieve the minimum necessary context.
5. Every result should be explainable and attributable.
6. Model instructions are not security boundaries.
7. MCP is an interface, not the product.
8. The organization should own its context independently of the model vendor.

## Planned reference stack

- Python 3.12+
- FastAPI
- PostgreSQL
- Pydantic
- Alembic
- OIDC/JWT
- MCP
- pytest
- Docker Compose
- GitHub Actions

The MVP will keep graph relationships in PostgreSQL rather than introduce a dedicated graph database prematurely.

## Documentation

- [Documentation index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Context model](docs/CONTEXT_MODEL.md)
- [Security model](docs/SECURITY.md)
- [Threat model](THREAT_MODEL.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Feature map](docs/FEATURE_MAP.md)
- [Verification loop](docs/VERIFICATION.md)
- [MVP evaluation report](docs/EVALUATION_REPORT.md)
- [Architecture decisions](docs/adr/)
- [Coding-agent demo](examples/coding-agent/README.md)
- [Copilot Studio demo](examples/copilot-studio/README.md)

## First milestone

A local service that can:

1. load versioned context items;
2. authenticate a principal;
3. resolve applicable context deterministically;
4. enforce policy precedence;
5. return provenance and an explanation trace;
6. expose the same resolver through REST and MCP.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

Please read [SECURITY.md](SECURITY.md) before reporting a vulnerability.

## License

Apache-2.0. See [LICENSE](LICENSE).
