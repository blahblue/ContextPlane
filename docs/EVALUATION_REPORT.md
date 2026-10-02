# MVP Evaluation Report

This report is generated from the reproducible ContextPlane evaluation harness in `contextplane.evaluation`.

The final benchmark baseline in this document is updated only from a green GitHub Actions run using PostgreSQL 16 and Python 3.12.

## Evaluation dimensions

The harness measures:

- warm runtime latency over 40 repeated governed resolutions;
- retrieval size and unexpected-context count for repository-scoped engineering context;
- exact-match accuracy across four golden resolution scenarios;
- mandatory-deny policy violations;
- stale-context behavior after immutable supersession with a warm cache;
- semantic consistency between REST and MCP clients using the same authenticated principal.

## Acceptance gates

The MVP passes only when:

- all four golden scenarios return the exact expected key sets;
- unexpected/over-retrieved context count is zero;
- policy-violation count is zero;
- a warm cache reflects an authoritative supersession immediately through context revisioning;
- REST and MCP return semantically equivalent effective context and policy decisions;
- warm runtime p95 latency is below 250 ms in GitHub Actions.

The 250 ms threshold is intentionally a broad regression guard for the reference MVP, not a production SLO.

## Golden scenarios

| Scenario | Expected context |
|---|---|
| checkout engineering | shared testing + checkout framework |
| catalog engineering | shared testing + catalog framework |
| checkout security | checkout secret-handling control |
| unknown repository | shared testing only |

## Baseline

Final values are populated from the final green PR-020 GitHub Actions run.

## Interpretation

The benchmark is deliberately small and deterministic. It verifies the correctness and client-consistency properties of the MVP and provides a latency regression signal.

It does **not** establish production throughput, multi-region performance, large-corpus scaling, connector performance, or an enterprise SLO. Those require load testing against a representative deployment and dataset.
