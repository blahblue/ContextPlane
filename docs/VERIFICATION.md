# Verification-First Engineering Loop

Every PR should follow the same loop.

## 1. Reconcile current behavior

Identify:

- current invariant;
- intended change;
- affected feature-map rows;
- affected ADRs/docs;
- any conflicts between code and documentation.

## 2. State verification before implementation

Define the checks first:

- unit;
- integration;
- contract;
- security;
- adversarial;
- manual demo, if needed.

## 3. Implement the smallest coherent change

Avoid bundling unrelated cleanup with behavior changes.

## 4. Verify schemas and contracts

Check:

- migrations;
- data validation;
- public interfaces;
- backward compatibility assumptions.

## 5. Verify authorization and policy

Check:

- least privilege;
- tenant isolation;
- mandatory-control behavior;
- negative paths.

## 6. Verify integration

Check:

- database;
- MCP;
- OIDC;
- adapters;
- caching.

## 7. Adversarial self-review

Attempt:

- bypass;
- over-retrieval;
- stale state;
- source poisoning;
- malformed identity;
- cross-tenant access.

## 8. Stranger-diff review

Read the PR as if unfamiliar with the repository.

Ask whether:

- names and boundaries are obvious;
- failures are safe and observable;
- security assumptions are explicit;
- docs match behavior;
- tests prove the intended invariant.

## 9. CI must be green

No merge with known failing checks.

## 10. Reconcile documentation

Update:

- feature map;
- architecture;
- ADRs;
- threat model;
- implementation plan, if sequencing changed.
