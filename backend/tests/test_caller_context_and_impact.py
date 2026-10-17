import os
import pytest
from app.agent.control_flow import ControlFlowAnalyzer
from app.agent.impact import ImpactAnalyzer
from app.agent.investigator import GraphInvestigator
from app.agent.pipeline import ReasoningPipeline, PathClassification

ORBIT_REPO_ID = "repo_orbitflow_asteri_1441ae"
ORBIT_REPO_PATH = "/home/zeraphynx/Projects/asterion/backend/data/repos/repo_orbitflow_asteri_1441ae/OrbitFlow_Benchmark"


@pytest.fixture
def control_flow():
    return ControlFlowAnalyzer(repo_path=ORBIT_REPO_PATH)


@pytest.fixture
def impact_analyzer():
    return ImpactAnalyzer(repo_id=ORBIT_REPO_ID, repo_path=ORBIT_REPO_PATH)


@pytest.fixture
def investigator():
    return GraphInvestigator(repo_id=ORBIT_REPO_ID, repo_path=ORBIT_REPO_PATH)


# ==============================================================================
# FIX 1 & FIX 2: Caller-Context Discovery & Cross-Function Exception Tracing
# ==============================================================================

def test_caller_context_discovery_create_label_to_dispatch(control_flow):
    """
    FIX 1: When analyzing create_label(), which contains no while/for loop,
    ControlFlowAnalyzer automatically discovers caller dispatch() via reverse CALLS
    traversal, switches target, and computes attempts and side effects.
    """
    res = control_flow.analyze_loop_and_retry(
        rel_path="orbitflow/carrier.py",
        function_name="create_label",
        max_retries_override=2,
        query="If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES = 2?"
    )

    assert res["status"] == "success"
    assert res["caller_context_used"] is True
    assert res["named_function"] == "create_label"
    assert res["behavioral_analysis_target"] == "dispatch"
    assert res["attempt_count"] == 3
    assert res["retry_count"] == 2
    assert res["loop_type"].lower() == "while"
    assert res["max_retries_constant"] == 2

    # Verify side effects captured from caller
    assert res["inventory_rollback"] is not None
    assert "release" in res["inventory_rollback"]
    assert res["customer_notification"] is not None
    assert "failed" in res["customer_notification"]
    assert "carrier_retry" in res["audit_events"]["per_retry"]
    assert "failed" in res["audit_events"]["on_exhaustion"]


def test_cross_function_source_grounded_execution_trace(control_flow):
    """
    FIX 2: Execution trace connects caller dispatch() and callee create_label()
    across 7 distinct, source-grounded steps.
    """
    res = control_flow.analyze_loop_and_retry(
        rel_path="orbitflow/carrier.py",
        function_name="create_label",
        max_retries_override=2,
        query="If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES = 2?"
    )

    trace = res.get("execution_trace", [])
    assert len(trace) >= 6

    # Verify trace steps contain required fields
    for step in trace:
        assert "step" in step
        assert "function" in step
        assert "citation" in step
        assert "statement" in step
        assert "outcome" in step
        assert "state_changes" in step
        assert "side_effects" in step

    # Step 1: Counter initialization
    assert trace[0]["step"] == 1
    assert "attempts" in trace[0]["statement"]

    # Step 3: Loop counter increment
    assert any("attempts += 1" in s["statement"] for s in trace)

    # Step 4: Callee invocation
    assert any("create_label" in s["statement"] for s in trace)

    # Step 5: Exception handling
    assert any("TimeoutError" in s["statement"] or "carrier_retry" in s["side_effects"] for s in trace)

    # Post-exhaustion cleanup: verify cleanup step is recorded with release side effect
    cleanup_step = next((s for s in trace if "release" in s.get("statement", "") or "release" in s.get("side_effects", "")), None)
    assert cleanup_step is not None
    # Ensure return statement does not inherit earlier cleanup side effects
    return_step = next((s for s in trace if "return" in s.get("statement", "")), None)
    if return_step:
        assert "release" not in return_step.get("side_effects", "")


def test_caller_context_ranking_multiple_callers(tmp_path):
    """
    FIX 1: Synthetic test verifying ranking when multiple callers exist:
    Caller with loop and exception handling ranks higher than caller without loop.
    """
    code_callee = "def send_packet(): raise ConnectionError('timeout')\n"
    code_caller_simple = "from callee import send_packet\ndef simple_caller(): send_packet()\n"
    code_caller_retry = """from callee import send_packet
MAX_RETRIES = 2
def retry_caller():
    attempts = 0
    while attempts <= MAX_RETRIES:
        try:
            attempts += 1
            send_packet()
        except ConnectionError:
            continue
    return 'exhausted'
"""
    callee_file = tmp_path / "callee.py"
    caller1_file = tmp_path / "caller_simple.py"
    caller2_file = tmp_path / "caller_retry.py"
    callee_file.write_text(code_callee)
    caller1_file.write_text(code_caller_simple)
    caller2_file.write_text(code_caller_retry)

    cf = ControlFlowAnalyzer(repo_path=str(tmp_path))
    res = cf.discover_behavioral_caller(
        target_function="send_packet",
        query="how many attempts occur when MAX_RETRIES = 2 and ConnectionError is raised?"
    )

    assert res is not None
    assert res["behavioral_function"] == "retry_caller"
    rankings = res.get("rankings", [])
    assert len(rankings) >= 1
    top_caller = rankings[0]
    assert top_caller["caller_function"] == "retry_caller"
    assert top_caller["has_loop"] is True
    assert top_caller["catches_target_exception"] is True
    assert top_caller["reads_config_constant"] is True


# ==============================================================================
# FIX 3: Execution-Aware Test Impact Analysis
# ==============================================================================

def test_execution_aware_test_impact_classification(impact_analyzer):
    """
    FIX 3: Classifies discovered tests into three execution-aware categories:
    - REGRESSION_DETECTING_TEST: test_carrier_failure_releases_stock (VERIFIED_COVERAGE)
    - BEHAVIORALLY_AFFECTED_TEST: test_successful_shipping, test_review_approval_ships (PARTIAL_COVERAGE)
    - STATICALLY_REACHABLE_TEST: test_vip_review_does_not_reserve (early return before dispatch)
    """
    res = impact_analyzer.analyze_symbol_impact("dispatch")

    # 1. Regression-detecting tests
    reg_tests = res.regression_detecting_tests
    assert any("test_carrier_failure_releases_stock" in t for t in reg_tests)
    assert any("test_carrier_failure_releases_stock" in t and res.coverage_status_map[t] == "VERIFIED_COVERAGE" for t in reg_tests)

    # 2. Behaviorally affected tests (normal success path without failure assertions)
    beh_tests = res.behaviorally_affected_tests
    assert any("test_successful_shipping" in t for t in beh_tests)
    assert any("test_review_approval_ships" in t for t in beh_tests)
    assert any("test_successful_shipping" in t and res.coverage_status_map[t] == "PARTIAL_COVERAGE" for t in beh_tests)

    # 3. Statically reachable tests (VIP scenario returns early before dispatch)
    stat_tests = res.statically_reachable_tests
    assert any("test_vip_review_does_not_reserve" in t for t in stat_tests)
    assert any("test_vip_review_does_not_reserve" in t and res.coverage_status_map[t] == "STATICALLY_REACHABLE_TEST" for t in stat_tests)


def test_no_existing_test_labeled_as_missing(impact_analyzer):
    """
    FIX 5: An existing verified test MUST NEVER be labeled as MISSING_COVERAGE.
    """
    res = impact_analyzer.analyze_symbol_impact("dispatch")

    for t in res.regression_detecting_tests:
        assert res.coverage_status_map[t] == "VERIFIED_COVERAGE"
        assert res.coverage_status_map[t] != "MISSING_COVERAGE"

    for t in res.behaviorally_affected_tests:
        assert res.coverage_status_map[t] == "PARTIAL_COVERAGE"
        assert res.coverage_status_map[t] != "MISSING_COVERAGE"


def test_genuine_coverage_gap_identified(impact_analyzer):
    """
    FIX 5: Manual review approval workflow lacks a carrier-failure test to assert
    stock restoration upon retry exhaustion. This is flagged as MISSING_COVERAGE.
    """
    res = impact_analyzer.analyze_symbol_impact("dispatch")

    gaps = res.coverage_gaps
    assert any("approve_review" in g and "MISSING_COVERAGE" in g for g in gaps)
    assert res.coverage_status_map.get("workflow_approve_review") == "MISSING_COVERAGE"
    assert res.coverage_status_map.get("workflow_submit_order") == "VERIFIED_COVERAGE"


# ==============================================================================
# FIX 4: Improve Hypothetical Impact Risk Scoring
# ==============================================================================

def test_deduplicated_risk_score_with_safety_credit(impact_analyzer):
    """
    FIX 4: Computes transparent risk score separating structural impact,
    behavioral impact, coverage gap penalty, and regression coverage credit.
    """
    res = impact_analyzer.analyze_symbol_impact("dispatch")

    assert res.risk_score > 0
    assert res.structural_impact_score > 0
    assert res.behavioral_impact_score > 0
    assert res.coverage_gap_penalty > 0
    assert res.regression_coverage_score > 0
    assert res.score_formula_explanation != ""

    # Verify score formula explanation is documented
    assert "Risk Score" in res.score_formula_explanation
    assert "Base" in res.score_formula_explanation
    assert "Structural" in res.score_formula_explanation
    assert "Behavioral" in res.score_formula_explanation
    assert "Regression Credit" in res.score_formula_explanation


# ==============================================================================
# FIX 6: Cross-Analyzer Consistency & Intermediate Representation
# ==============================================================================

def test_cross_analyzer_shared_ir_consistency(investigator):
    """
    FIX 6: Shared reasoning intermediate representation preserves caller-context
    reconciliation and test classifications without contradictory assertions.
    """
    pipeline = investigator.pipeline
    pdata = pipeline.run("If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES = 2?")

    shared_ir = pdata.get("shared_ir", {})
    assert shared_ir.get("caller_context_used") is True
    assert shared_ir.get("named_function") == "create_label"
    assert shared_ir.get("behavioral_analysis_target") == "dispatch"
    assert len(shared_ir.get("execution_traces", [])) >= 6


# ==============================================================================
# FIX 7: End-to-End Benchmark Questions Answer Quality
# ==============================================================================

def test_orbitflow_q2_retry_attempts_and_side_effects(investigator):
    """
    OrbitFlow Benchmark Question 2:
    'If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES = 2?
    Explain the audit events, inventory changes, and notifications.'
    """
    ans = investigator.investigate(
        "If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES = 2? "
        "Explain the audit events, inventory changes, and notifications."
    )

    # 1. Direct answer upfront
    assert "3 attempts" in ans or "3" in ans
    # 2. Caller-context explanation
    assert "create_label" in ans
    assert "dispatch" in ans
    # 3. Audit events
    assert "carrier_retry" in ans
    assert "failed" in ans
    # 4. Inventory release
    assert "release" in ans
    # 5. Customer notification
    assert "notify_customer" in ans
    # 6. Source citations
    assert "orbitflow/dispatch.py" in ans
    # 7. No raw internal symbols
    assert "sym_repo_orbitflow_" not in ans


def test_orbitflow_q4_impact_and_test_differentiation(investigator):
    """
    OrbitFlow Benchmark Question 4:
    'If dispatch() stops calling release() on exhausted retries, which workflows and tests are affected?
    Distinguish automatic orders from manually approved orders.'
    """
    ans = investigator.investigate(
        "If dispatch() stops calling release() on exhausted retries, which workflows and tests are affected? "
        "Distinguish automatic orders from manually approved orders."
    )

    # 1. Both workflows identified
    assert "submit_order" in ans
    assert "approve_review" in ans
    # 2. Regression detecting test identified
    assert "test_carrier_failure_releases_stock" in ans
    # 3. Missing test coverage for manual approval identified
    assert "test_review.py" in ans or "approve_review" in ans
    # 4. Consistent terminology used
    assert "VERIFIED_COVERAGE" in ans or "Regression-Detecting" in ans
    assert "MISSING_COVERAGE" in ans
    # 5. No raw symbols
    assert "sym_repo_orbitflow_" not in ans
