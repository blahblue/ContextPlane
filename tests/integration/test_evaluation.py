import pytest

from contextplane.database import build_engine
from contextplane.evaluation import run_evaluation
from contextplane.settings import Settings

pytestmark = pytest.mark.integration


def test_mvp_evaluation_meets_acceptance_gates() -> None:
    engine = build_engine(Settings())
    try:
        report = run_evaluation(engine)
    finally:
        engine.dispose()

    assert report.passed
    assert report.golden_scenarios_passed == report.golden_scenarios_total == 4
    assert report.rule_accuracy == 1.0
    assert report.unexpected_context_items == 0
    assert report.over_retrieval_rate == 0.0
    assert report.policy_violations == 0
    assert report.stale_context_pass
    assert report.rest_mcp_consistent
    assert report.warm_runtime_p95_ms < 250.0
