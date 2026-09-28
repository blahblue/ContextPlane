# Feature Map

Status values: **planned**, **partial**, **implemented**, **verified**, **deferred**.

| Area | Feature | MVP | Status | Verification |
|---|---|---:|---|---|
| Foundation | Python package scaffold | Yes | verified | CI install + import |
| Foundation | FastAPI health endpoint | Yes | verified | API tests |
| Foundation | Lint / type / test CI | Yes | verified | GitHub Actions run 36442725339 |
| Foundation | Containerized local service | Yes | verified | Docker definition review + CI package verification |
| Persistence | PostgreSQL reference service | Yes | verified | GitHub Actions PostgreSQL service |
| Persistence | Environment-driven DB configuration | Yes | verified | settings validation + fail-closed tests |
| Persistence | Alembic migration boundary | Yes | verified | CI migration on empty database |
| Persistence | Database readiness integration | Yes | verified | real PostgreSQL integration test |
| Registry | Context item schema | Yes | verified | Pydantic + PostgreSQL constraints |
| Registry | Scope schema | Yes | verified | strict validation + tenant DB constraint |
| Registry | Context item CRUD | Yes | planned | API + DB integration |
| Registry | Immutable versioning | Yes | verified | insert-only history + PostgreSQL lineage constraints |
| Registry | Provenance schema | Yes | verified | typed source fields + DB constraints |
| Graph | Typed relationships | Yes | verified | tenant-scoped logical edges + PostgreSQL FK/adversarial tests |
| Resolver | Hierarchical scope | Yes | verified | scope matching + wildcard/missing-dimension tests |
| Resolver | Authority levels | Yes | implemented | authority/override matrix + fail-closed tie tests |
| Resolver | Explanation trace | Yes | verified | deterministic candidate explanations |
| Policy | Allow / deny | Yes | planned | adversarial tests |
| Policy | Mandatory controls | Yes | planned | override rejection |
| Identity | OIDC | Yes | planned | token validation |
| Identity | Entra adapter | Yes | planned | tenant fixture |
| Identity | Agent identity | Yes | planned | user/agent separation |
| Runtime | REST resolver | Yes | planned | end-to-end |
| Runtime | MCP server | Yes | planned | MCP contract tests |
| Runtime | Python SDK | Yes | planned | SDK integration |
| Audit | Resolution log | Yes | planned | audit completeness |
| Client | Coding-agent demo | Yes | planned | reproducible scenario |
| Client | Copilot Studio demo | Yes | planned | reproducible scenario |
| Sources | YAML seed | Yes | verified | canonical checksum + idempotency + immutable supersession |
| Sources | Git adapter | No | deferred | — |
| Sources | SharePoint adapter | No | deferred | — |
| Sources | Databricks adapter | No | deferred | — |
| Sources | Fabric adapter | No | deferred | — |
| UI | Admin graph editor | No | deferred | — |
| UI | Audit viewer | No | deferred | — |
| Personal | Personal context gateway | No | deferred | — |

Update this table in the same PR whenever a feature's implementation state changes.
