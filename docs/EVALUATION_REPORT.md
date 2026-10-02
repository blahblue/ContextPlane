# MVP Evaluation Report

This report is generated from the reproducible ContextPlane evaluation harness in `contextplane.evaluation`.

The baseline below comes from GitHub Actions run **36990742946** using Python 3.12 and PostgreSQL 16.

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
- a warm cache reflects an authoritative supersession through context revisioning;
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

## Baseline — GitHub Actions 36990742946

| Metric | Result | Gate |
|---|---:|---:|
| Warm runtime iterations | 40 | 40 |
| Warm runtime p50 | **2.084 ms** | informational |
| Warm runtime p95 | **3.775 ms** | < 250 ms |
| Returned checkout context items | **2** | expected 2 |
| Unexpected context items | **0** | 0 |
| Over-retrieval rate | **0.0%** | 0% |
| Golden scenarios | **4 / 4** | 4 / 4 |
| Rule accuracy | **100%** | 100% |
| Policy violations | **0** | 0 |
| Stale-context refresh | **pass** | pass |
| REST/MCP semantic consistency | **pass** | pass |
| Evaluation result | **pass** | pass |

The same CI run completed **255 tests** at **95.01% code coverage**, above the repository's 90% coverage requirement.

## Reproduce

With PostgreSQL configured through `CONTEXTPLANE_DATABASE_URL` and migrations applied:

```bash
python -m contextplane.evaluation
```

The command prints one machine-readable JSON object and exits non-zero when an acceptance gate fails. CI runs it after the normal test suite.

## Interpretation

The benchmark verifies the MVP's correctness, retrieval discipline, cache freshness, policy enforcement, and REST/MCP consistency while providing a lightweight latency regression signal.

It does **not** establish:

- production throughput or concurrency capacity;
- multi-region latency;
- large-corpus scaling characteristics;
- external connector performance;
- a production availability or latency SLO;
- model compliance with returned instructions;
- authorization to underlying resources from context selectors.

Those require separate production/load testing and enforceable downstream resource boundaries.
