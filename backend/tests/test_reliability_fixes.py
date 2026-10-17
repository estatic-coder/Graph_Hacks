import pytest
import os
import ast
import tempfile
from app.agent.control_flow import ControlFlowAnalyzer, PathClassification, PathFeasibilityResult
from app.agent.intent import IntentClassifier
from app.agent.impact import ImpactAnalyzer
from app.agent.pipeline import ReasoningPipeline
from app.agent.investigator import GraphInvestigator
from app.repositories.manager import RepositoryManager

ORBIT_REPO_ID = "repo_orbitflow_asteri_1441ae"

@pytest.fixture
def orbit_control_flow():
    meta = RepositoryManager().get_repository(ORBIT_REPO_ID)
    return ControlFlowAnalyzer(repo_path=meta.source_path if meta else None)

@pytest.fixture
def orbit_pipeline():
    return ReasoningPipeline(repo_id=ORBIT_REPO_ID)

@pytest.fixture
def orbit_investigator():
    return GraphInvestigator(repo_id=ORBIT_REPO_ID)


# ============================================================================
# FIX 3: Path Classifications
# ============================================================================

def test_fix3_path_classification_static_call_paths(orbit_control_flow):
    """
    Verifies pure directed CALLS edge chains are classified as STATIC_CALL_PATH:
    1. create_order -> submit_order -> dispatch -> create_label (without scenario constraint)
    2. approve_review -> dispatch -> create_label
    """
    path_1 = [
        {"name": "create_order", "path": "orbitflow/api.py"},
        {"name": "submit_order", "path": "orbitflow/workflow.py"},
        {"name": "dispatch", "path": "orbitflow/dispatch.py"},
        {"name": "create_label", "path": "orbitflow/carrier.py"}
    ]
    res_1 = orbit_control_flow.evaluate_path_feasibility(path_1, query="Show the call path from create_order to create_label")
    assert res_1.classification == PathClassification.STATIC_CALL_PATH
    assert res_1.is_feasible is True

    path_2 = [
        {"name": "approve_review", "path": "orbitflow/manual_review.py"},
        {"name": "dispatch", "path": "orbitflow/dispatch.py"},
        {"name": "create_label", "path": "orbitflow/carrier.py"}
    ]
    res_2 = orbit_control_flow.evaluate_path_feasibility(path_2, query="Trace approve_review to create_label")
    assert res_2.classification == PathClassification.STATIC_CALL_PATH
    assert res_2.is_feasible is True


def test_fix3_path_classification_infeasible_for_vip(orbit_control_flow):
    """
    Verifies that under VIP scenario, create_order -> submit_order -> dispatch -> create_label
    is classified as INFEASIBLE_PATH due to early return in submit_order.
    """
    path_vip = [
        {"name": "create_order", "path": "orbitflow/api.py"},
        {"name": "submit_order", "path": "orbitflow/workflow.py"},
        {"name": "dispatch", "path": "orbitflow/dispatch.py"},
        {"name": "create_label", "path": "orbitflow/carrier.py"}
    ]
    query = "For a VIP customer order, does create_order execute through to create_label?"
    res = orbit_control_flow.evaluate_path_feasibility(path_vip, query=query)
    assert res.classification == PathClassification.INFEASIBLE_PATH
    assert res.is_feasible is False
    assert res.blocking_guard is not None
    assert res.blocking_guard["function"] == "submit_order"
    assert res.state_mediated_workflow is not None


def test_fix3_path_classification_state_mediated_workflow(orbit_control_flow):
    """
    Verifies that paths explicitly connecting separate execution entry points
    through state are classified as STATE_MEDIATED_WORKFLOW.
    """
    path_connected = [
        {"name": "create_order", "path": "orbitflow/api.py"},
        {"name": "submit_order", "path": "orbitflow/workflow.py"},
        {"name": "approve_review", "path": "orbitflow/manual_review.py"},
        {"name": "dispatch", "path": "orbitflow/dispatch.py"},
        {"name": "create_label", "path": "orbitflow/carrier.py"}
    ]
    res = orbit_control_flow.evaluate_path_feasibility(
        path_connected,
        query="Connect create_order through review state to approve_review"
    )
    assert res.classification == PathClassification.STATE_MEDIATED_WORKFLOW
    assert res.is_feasible is True
    assert res.state_mediated_workflow["is_state_mediated"] is True


def test_fix3_path_classification_unverified_workflow():
    """
    Verifies UNVERIFIED_WORKFLOW is used when a proposed workflow cannot be verified.
    """
    cf = ControlFlowAnalyzer(repo_path="/nonexistent")
    path = [{"name": "unknown_a"}, {"name": "unknown_b"}]
    res = PathFeasibilityResult(
        path_str="unknown_a -> unknown_b",
        classification=PathClassification.UNVERIFIED_WORKFLOW,
        is_feasible=False,
        explanation="Workflow cannot be verified from available graph and source evidence."
    )
    assert res.classification == PathClassification.UNVERIFIED_WORKFLOW
    assert res.is_feasible is False


# ============================================================================
# FIX 4: Hypothetical Change-Impact Analysis
# ============================================================================

def test_fix4_hypothetical_impact_dispatch_release(orbit_pipeline):
    """
    Query: "If dispatch() stops calling release() after exhausting carrier retries, which workflows and tests are affected?"
    Verifies:
    1. Intent is CHANGE_IMPACT_ANALYSIS.
    2. Mode is HYPOTHETICAL_IMPACT.
    3. Target symbol is resolved to 'dispatch'.
    4. Risk score > 0.
    5. Direct callers include submit_order and approve_review.
    6. Identifies coverage gap between test_workflow.py and test_review.py.
    """
    q = "If dispatch() stops calling release() after exhausting carrier retries, which workflows and tests are affected?"
    res = orbit_pipeline.run(q)

    assert res["intent"] in ("CHANGE_IMPACT_ANALYSIS", "IMPACT_ANALYSIS")
    assert "impact_analysis" in res["traversal_results"]

    imp = res["traversal_results"]["impact_analysis"]
    assert imp.mode == "HYPOTHETICAL_IMPACT"
    assert imp.target_symbol == "dispatch"
    assert imp.risk_score > 0
    assert "submit_order" in imp.direct_callers
    assert "approve_review" in imp.direct_callers
    assert any("test_review.py" in g for g in imp.coverage_gaps)


def test_fix4_hypothetical_natural_language_triggers():
    """
    Verifies entity extraction and intent classification for various natural language
    hypothetical change formulations.
    """
    ic = IntentClassifier()

    cases = [
        ("What if process_payment() stops calling charge_gateway()?", "process_payment"),
        ("If validate_token() is removed, which callers break?", "validate_token"),
        ("Suppose fetch_record() returns None, what is the impact?", "fetch_record"),
        ("Which tests break if delete_user() is deleted?", "delete_user"),
        ("If dispatch() stops calling release(), what happens?", "dispatch"),
    ]

    for query, expected_target in cases:
        result = ic.classify(query)
        assert result.primary_intent in ("CHANGE_IMPACT_ANALYSIS", "IMPACT_ANALYSIS", "HYPOTHETICAL_IMPACT"), f"Failed for {query}"
        assert any(expected_target in c for c in result.candidate_entities), f"Target {expected_target} not in candidates for {query}"


# ============================================================================
# FIX 5: Structured Analyzer Contracts Schema & Status
# ============================================================================

def test_fix5_structured_output_schema_compliance(orbit_control_flow):
    """
    Verifies analyze_loop_and_retry returns all required schema fields:
    status, target_function, file_path, loop_type, loop_condition,
    counter_initialization, counter_update, configuration_values,
    exception_handlers, early_exits, attempt_count, side_effects,
    source_evidence, limitations.
    """
    data = orbit_control_flow.analyze_loop_and_retry("orbitflow/dispatch.py", "dispatch")

    # Required top-level keys
    required_keys = [
        "status", "target_function", "file_path", "loop_type", "loop_condition",
        "counter_initialization", "counter_update", "configuration_values",
        "exception_handlers", "early_exits", "attempt_count", "side_effects",
        "source_evidence", "limitations"
    ]
    for k in required_keys:
        assert k in data, f"Missing required key: {k}"

    assert data["status"] == "success"
    assert data["target_function"] == "dispatch"
    assert data["loop_type"] == "while"
    assert "attempts" in data["loop_condition"]
    assert data["attempt_count"] == 3
    assert data["max_possible_iterations"] == 3
    assert data["retry_count"] == 2
    assert isinstance(data["configuration_values"], dict)
    assert isinstance(data["exception_handlers"], list)
    assert isinstance(data["side_effects"], list)
    assert len(data["side_effects"]) > 0


def test_fix5_analyzer_explicit_failure_status():
    """
    Verifies that when given a non-existent function or file without loops,
    analyze_loop_and_retry returns explicit status='error' with diagnostic_reason,
    NOT placeholder None strings pretending to be verified.
    """
    cf = ControlFlowAnalyzer(repo_path="/tmp")
    data = cf.analyze_loop_and_retry("nonexistent.py", "no_such_function")

    assert data["status"] == "error"
    assert data["target_function"] == "no_such_function"
    assert data["diagnostic_reason"] is not None
    assert len(data["limitations"]) > 0
    assert data["attempt_count"] is None
    assert data["loop_type"] is None


# ============================================================================
# FIX 6: Cross-Analyzer Consistency Verification
# ============================================================================

def test_fix6_cross_analyzer_contradiction_detection(orbit_pipeline):
    """
    Verifies that cross-analyzer contradictions are caught in the shared IR:
    1. Static path reachability contradiction when path is infeasible.
    2. Early return in exception handler contradiction.
    """
    q = "Trace a VIP order from create_order() to create_label()."
    res = orbit_pipeline.run(q)

    shared_ir = res["shared_ir"]
    contradictions = shared_ir.get("contradictions_detected", [])
    assert len(contradictions) > 0
    assert any("Static path reachability contradiction" in c for c in contradictions)


# ============================================================================
# GENERALIZATION: Synthetic Repository with Unfamiliar Function/Variable Names
# ============================================================================

def test_generalization_synthetic_unfamiliar_repository():
    """
    Tests AST loop and retry analysis on completely synthetic code with
    unfamiliar domain names (e.g. quantum pipeline, nebula sensors, tau counters).
    Ensures zero hardcoding of OrbitFlow/AegisOps/SentinelShop identifiers.
    """
    synthetic_code = '''
TAU_MAX_TRIES = 4

def execute_quantum_probe(sensor_id):
    probe_ticks = 0
    sensor_calibrated = False
    
    while probe_ticks < TAU_MAX_TRIES:
        probe_ticks += 1
        try:
            sample_nebula_wave(sensor_id)
            sensor_calibrated = True
            return True
        except ResonanceMismatchError:
            log_telemetry_event(sensor_id, "retry_phase")
    
    purge_quantum_buffer(sensor_id)
    return False
'''
    with tempfile.TemporaryDirectory() as tmp_dir:
        synth_file = os.path.join(tmp_dir, "nebula_probe.py")
        with open(synth_file, "w", encoding="utf-8") as f:
            f.write(synthetic_code)

        analyzer = ControlFlowAnalyzer(repo_path=tmp_dir)

        # 1. Analyze by function name
        res = analyzer.analyze_loop_and_retry("nebula_probe.py", "execute_quantum_probe")
        assert res["status"] == "success"
        assert res["target_function"] == "execute_quantum_probe"
        assert res["loop_type"] == "while"
        assert "TAU_MAX_TRIES" in res["loop_condition"] or "probe_ticks <" in res["loop_condition"]
        assert res["counter_update_position"] == "before_call"
        # Condition is '< TAU_MAX_TRIES' with limit 4, starting at 0 -> 4 attempts
        assert res["max_possible_iterations"] == 4
        assert res["attempt_count"] == 4
        assert res["retry_count"] == 3

        # Side effects in execution order
        stmt_types = [se["statement"] for se in res["side_effects"]]
        assert any("sample_nebula_wave" in s for s in stmt_types)
        assert any("log_telemetry_event" in s for s in stmt_types)
        assert any("purge_quantum_buffer" in s for s in stmt_types)

        # 2. Analyze by config variable name (e.g. user asks about TAU_MAX_TRIES)
        res_cfg = analyzer.analyze_loop_and_retry("", "TAU_MAX_TRIES")
        assert res_cfg["status"] == "success"
        assert res_cfg["target_function"] == "execute_quantum_probe"
        assert res_cfg["attempt_count"] == 4
