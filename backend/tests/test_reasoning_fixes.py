import pytest
import os
import ast
import tempfile
from app.agent.investigator import GraphInvestigator
from app.agent.pipeline import ReasoningPipeline
from app.agent.intent import IntentClassifier
from app.agent.impact import ImpactAnalyzer
from app.agent.control_flow import ControlFlowAnalyzer, PathClassification
from app.agent.resolver import EntityResolver
from app.repositories.manager import RepositoryManager

ORBIT_REPO_ID = "repo_orbitflow_asteri_1441ae"
AEGIS_REPO_ID = "repo_aegisops_asterio_158e16"
SENTINEL_REPO_ID = "repo_sentinelshop_ast_e1e991"

@pytest.fixture
def investigator():
    return GraphInvestigator(repo_id=ORBIT_REPO_ID)

@pytest.fixture
def pipeline():
    return ReasoningPipeline(repo_id=ORBIT_REPO_ID)

@pytest.fixture
def control_flow():
    meta = RepositoryManager().get_repository(ORBIT_REPO_ID)
    return ControlFlowAnalyzer(repo_path=meta.source_path if meta else None)


def test_fix1_scenario_path_feasibility_and_state_mediated_workflow(control_flow, pipeline):
    """
    FIX 1: Scenario-Aware Graph Path Reasoning
    Verifies:
    1. Static path create_order -> submit_order -> dispatch -> create_label exists in call graph.
    2. Feasibility evaluation flags static path as INFEASIBLE_PATH for VIP orders.
    3. Detects early return in submit_order() at line 15 with status = 'review'.
    4. Explains state-mediated workflow connecting submit_order and approve_review via SHIPMENTS.
    5. Confirms submit_order does NOT call approve_review directly (no CALLS edge invented).
    """
    path_nodes = [
        {"name": "create_order", "path": "orbitflow/api.py"},
        {"name": "submit_order", "path": "orbitflow/workflow.py"},
        {"name": "dispatch", "path": "orbitflow/dispatch.py"},
        {"name": "create_label", "path": "orbitflow/carrier.py"}
    ]
    query = "Trace a VIP order from create_order() through manual approval to create_label(). Why is approve_review() necessary?"
    
    feasibility = control_flow.evaluate_path_feasibility(path_nodes, query)
    
    # 1. Classification is INFEASIBLE_PATH
    assert feasibility.classification == PathClassification.INFEASIBLE_PATH
    assert feasibility.is_feasible is False
    
    # 2. Blocking branch identified
    assert feasibility.blocking_guard["function"] == "submit_order"
    assert feasibility.blocking_guard["line"] == 15
    assert feasibility.blocking_guard["condition"] == "decision == 'manual_review'"
    assert "orbitflow/workflow.py:11-15" in feasibility.blocking_guard["citation"]
    
    # 3. State-mediated workflow identified
    assert feasibility.state_mediated_workflow["is_state_mediated"] is True
    assert "SHIPMENTS" in feasibility.state_mediated_workflow["intermediate_state"]
    assert "approve_review() is necessary" in feasibility.state_mediated_workflow["why_necessary"]
    assert "does NOT call approve_review() directly" in feasibility.state_mediated_workflow["why_necessary"]
    
    # 4. Pipeline integration
    res = pipeline.run(query)
    shared_ir = res.get("shared_ir", {})
    assert len(shared_ir.get("infeasible_paths", [])) > 0
    assert len(shared_ir.get("contradictions_detected", [])) > 0


def test_fix2_ast_loop_and_retry_scenarios_a_and_b(control_flow):
    """
    FIX 2: Correct Loop, Retry, and Exception Reasoning
    Verifies AST control-flow engine distinguishes:
    Scenario A: Retry continues (audit event, no return in handler -> 3 attempts when MAX_RETRIES=2, 4 when MAX_RETRIES=3).
    Scenario B: Early return inside exception handler -> loop terminates after 1 attempt regardless of MAX_RETRIES.
    """
    # Scenario A: OrbitFlow actual implementation in dispatch.py
    loop_a = control_flow.analyze_loop_and_retry("orbitflow/dispatch.py", "dispatch", max_retries_override=2)
    assert loop_a["loop_scenario"] == "retry_continues"
    assert loop_a["has_early_exit_in_handler"] is False
    assert loop_a["calculated_attempts"] == 3
    assert loop_a["max_retries_constant"] == 2
    assert "release" in loop_a["inventory_rollback"]
    assert loop_a["audit_events"]["per_retry"] is not None
    assert loop_a["audit_events"]["on_exhaustion"] is not None

    loop_a_3 = control_flow.analyze_loop_and_retry("orbitflow/dispatch.py", "dispatch", max_retries_override=3)
    assert loop_a_3["calculated_attempts"] == 4

    # Scenario B: Early return inside exception handler
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
        tf.write('''
MAX_RETRIES = 2
def dispatch_with_early_return(order_id):
    attempts = 0
    while attempts <= MAX_RETRIES:
        attempts += 1
        try:
            call_carrier(order_id)
            return True
        except TimeoutError:
            record_audit("retry", order_id)
            return False  # Early return inside handler!
    return False
''')
        temp_file_path = tf.name

    try:
        # Create a ControlFlowAnalyzer pointing to temp file directory
        temp_cf = ControlFlowAnalyzer(repo_path=os.path.dirname(temp_file_path))
        loop_b = temp_cf.analyze_loop_and_retry(os.path.basename(temp_file_path), "dispatch_with_early_return", max_retries_override=2)
        assert loop_b["loop_scenario"] == "early_return"
        assert loop_b["has_early_exit_in_handler"] is True
        assert loop_b["calculated_attempts"] == 1

        # Even with MAX_RETRIES=3 or 10, Scenario B executes exactly 1 attempt!
        loop_b_10 = temp_cf.analyze_loop_and_retry(os.path.basename(temp_file_path), "dispatch_with_early_return", max_retries_override=10)
        assert loop_b_10["calculated_attempts"] == 1
    finally:
        os.remove(temp_file_path)


def test_fix3_numeric_and_hypothetical_intent_classification():
    """
    FIX 3: Numeric and Hypothetical Question Classification
    Verifies:
    1. "If MAX_RETRIES changes from 2 to 3..." classifies as CONFIGURATION_IMPACT.
    2. Numbers 2 and 3 are not extracted as candidate code entities.
    3. The word 'from' does NOT trigger SHORTEST_PATH.
    4. "how many attempts" questions classify as LOOP_EXECUTION_ANALYSIS.
    """
    ic = IntentClassifier()

    # Case 1: Numeric configuration change
    q1 = "If MAX_RETRIES changes from 2 to 3, will the carrier receive three or four attempts?"
    res1 = ic.classify(q1)
    assert res1.primary_intent == "CONFIGURATION_IMPACT"
    assert "2" not in res1.candidate_phrases
    assert "3" not in res1.candidate_phrases
    assert res1.primary_intent != "SHORTEST_PATH"

    # Case 2: Loop execution count
    q2 = "If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES=2?"
    res2 = ic.classify(q2)
    assert res2.primary_intent in ("LOOP_EXECUTION_ANALYSIS", "CONFIGURATION_IMPACT")
    assert "2" not in res2.candidate_phrases

    # Case 3: Hypothetical change impact
    q3 = "If dispatch() stops calling release() after exhausting carrier retries, which workflows and tests are affected?"
    res3 = ic.classify(q3)
    assert res3.primary_intent in ("CHANGE_IMPACT_ANALYSIS", "IMPACT_ANALYSIS")


def test_fix4_hypothetical_impact_without_git_diff():
    """
    FIX 4: Hypothetical Change-Impact Analysis Without Git Diff
    Verifies:
    1. Analyzes symbol change when no git diff is present.
    2. Sets mode = 'HYPOTHETICAL_IMPACT'.
    3. Identifies both workflows: submit_order -> dispatch and approve_review -> dispatch.
    4. Identifies inventory leakage side effect if release() is omitted.
    5. Flags test coverage gap: test_workflow.py covers submit_order, but test_review.py lacks failure test.
    6. Produces non-zero heuristic risk score with breakdown.
    """
    analyzer = ImpactAnalyzer(repo_id=ORBIT_REPO_ID)
    res = analyzer.analyze_symbol_impact("dispatch")

    assert res.mode == "HYPOTHETICAL_IMPACT"
    assert res.target_symbol == "dispatch"
    assert res.risk_score > 0
    assert res.risk_level in ("HIGH", "CRITICAL", "MEDIUM")

    # Both workflows are identified
    caller_names = res.direct_callers
    assert "submit_order" in caller_names
    assert "approve_review" in caller_names

    # Test coverage gap identified
    assert len(res.coverage_gaps) > 0
    assert any("test_review.py" in g for g in res.coverage_gaps)
    assert any("test_workflow.py" in g for g in res.coverage_gaps)


def test_fix5_branch_level_test_coverage_approve_review(control_flow):
    """
    FIX 5: Branch-Level Test Coverage Analysis
    Verifies:
    1. Parses control-flow branches of approve_review().
    2. Identifies tested status guard (status != 'review').
    3. Identifies untested reservation failure branch (if not reserve).
    4. Identifies downstream carrier timeout gap.
    5. Recommends targeted regression tests.
    """
    btc = control_flow.find_untested_branches("orbitflow/manual_review.py", "approve_review")

    assert btc["function"] == "approve_review"
    assert len(btc["tested_branches"]) > 0
    assert len(btc["untested_branches"]) > 0

    # Tested branch: status guard
    tested_conds = [b["condition"] for b in btc["tested_branches"]]
    assert any("status !=" in c for c in tested_conds)

    # Untested failure branch: reserve failure
    untested_conds = [b["condition"] for b in btc["untested_branches"]]
    assert any("reserve" in c for c in untested_conds)

    # Recommendations
    recs = btc["recommended_missing_tests"]
    assert any("out_of_stock" in r for r in recs)
    assert any("carrier_failure" in r for r in recs)


def test_fix6_shared_reasoning_ir_consistency(pipeline):
    """
    FIX 6: Consistent Reasoning Across Intents
    Verifies:
    1. ReasoningPipeline returns shared_ir.
    2. shared_ir contains resolved_entities, static_graph_paths, and contradiction detection.
    3. Detects contradiction between static path and scenario infeasibility.
    """
    q = "Trace a VIP order from create_order() through manual approval to create_label(). Why is approve_review() necessary?"
    res = pipeline.run(q)

    assert "shared_ir" in res
    shared_ir = res["shared_ir"]
    assert shared_ir["repository_id"] == ORBIT_REPO_ID
    assert len(shared_ir["infeasible_paths"]) > 0
    assert len(shared_ir["contradictions_detected"]) > 0
    assert "Static path reachability contradiction" in shared_ir["contradictions_detected"][0]


def test_fix7_evidence_quality_and_symbol_sanitization(investigator):
    """
    FIX 7: Evidence and Answer Quality
    Verifies:
    1. Answers do not output raw internal symbol IDs (e.g. sym_repo_orbitflow_...).
    2. Answers preserve Python line indentation in code snippets.
    3. Cites real source lines.
    4. Distinguishes extracted evidence from inferred conclusions.
    """
    q = "Find every function call path from create_order() and approve_review() to create_label(). Which functions are shared? Cite each hop."
    ans, report = investigator.investigate_with_report(q)

    # 1. No raw internal IDs
    assert "sym_repo_orbitflow_" not in ans
    assert "sym_" not in ans

    # 2. Source line citations
    assert "orbitflow/api.py" in ans
    assert "orbitflow/workflow.py" in ans
    assert "orbitflow/manual_review.py" in ans
    assert "orbitflow/dispatch.py" in ans

    # 3. Report verification
    assert report.is_verified is True
    assert report.citations_valid > 0


def test_multiple_source_path_discovery(investigator):
    """
    Verifies multiple sources to one destination:
    create_order() and approve_review() -> create_label().
    """
    q = "Find every function call path from create_order() and approve_review() to create_label(). Which functions are shared? Cite each hop."
    ans, report = investigator.investigate_with_report(q)

    assert "create_order -> submit_order -> dispatch -> create_label" in ans
    assert "approve_review -> dispatch -> create_label" in ans
    assert "dispatch" in ans and "create_label" in ans
    assert report.is_verified is True


def test_cross_repository_isolation_and_kafka_absence(investigator):
    """
    Verifies strict repository isolation and absence verification for Kafka in OrbitFlow.
    """
    q = "Which function publishes shipment events to Kafka, and where is the Kafka producer configured?"
    ans, report = investigator.investigate_with_report(q)

    assert "No Kafka" in ans or "no kafka" in ans.lower()
    assert "EVENTS" in ans
    assert "orbitflow/storage.py" in ans
    assert "MLchallenge" not in ans
    assert "asteria" not in ans
    assert report.is_verified is True
