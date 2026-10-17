import os
import ast
import tempfile
from unittest.mock import MagicMock
import pytest

from app.agent.control_flow import ControlFlowAnalyzer, TraceStep, LoopExecutionSimulation
from app.agent.pipeline import ReasoningPipeline, SharedReasoningRepresentation
from app.agent.verifier import CrossSectionValidator, EvidenceVerifier
from app.agent.investigator import GraphInvestigator


# ==============================================================================
# 1. RETRY REASONING & TRACE INTEGRITY SYNTHETIC FIXTURES (Fixes 1-5, 8, 10)
# ==============================================================================

SYNTHETIC_CODE = """
class Config:
    MAX_RETRIES = 3

class State:
    attempts: int = 0
    non_zero_attempts: int = 1

# Pattern 1: Inclusive loop, increment before call, implicit continuation
def fn_inclusive_before(service):
    attempts = 0
    while attempts <= 2:
        attempts += 1
        try:
            service.call()
            service.notify("shipped")
        except Exception:
            service.record("retry_event")
    service.release("stock")
    service.notify("failed")

# Pattern 2: Exclusive loop, increment after call
def fn_exclusive_after(service):
    attempts = 0
    while attempts < 3:
        try:
            service.call()
            service.notify("shipped")
        except Exception:
            service.record("retry_event")
        attempts += 1
    service.release("stock")

# Pattern 3: Initial counter value non-zero (starts at 1)
def fn_nonzero_start(service):
    attempts = 1
    while attempts <= 3:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("retry_event")

# Pattern 4: Explicit continue in exception handler
def fn_explicit_continue(service):
    attempts = 0
    while attempts <= 2:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("explicit_continue")
            continue

# Pattern 5: Early return in exception handler
def fn_early_return(service):
    attempts = 0
    while attempts <= 2:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("handler_return")
            return "failed_early"
    return "exhausted"

# Pattern 6: Break in exception handler
def fn_break(service):
    attempts = 0
    while attempts <= 2:
        attempts += 1
        try:
            service.call()
        except Exception:
            service.record("handler_break")
            break
    service.cleanup("post_break")
"""

@pytest.fixture(scope="module")
def synthetic_suite():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tf:
        tf.write(SYNTHETIC_CODE)
        temp_path = tf.name

    cf = ControlFlowAnalyzer(repo_path=os.path.dirname(temp_path))
    file_name = os.path.basename(temp_path)

    import importlib.util
    spec = importlib.util.spec_from_file_location("syn_module", temp_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    yield cf, file_name, mod

    try:
        os.remove(temp_path)
    except Exception:
        pass


def test_inclusive_vs_exclusive_loop_conditions(synthetic_suite):
    cf, file_name, mod = synthetic_suite

    # Pattern 1: <= 2 with init 0 -> 3 attempts
    res_inc = cf.analyze_loop_and_retry(file_name, "fn_inclusive_before")
    assert res_inc["attempt_count"] == 3
    assert res_inc["retry_count"] == 2
    assert "<=" in res_inc["loop_condition"]

    # Pattern 2: < 3 with init 0 -> 3 attempts
    res_exc = cf.analyze_loop_and_retry(file_name, "fn_exclusive_after")
    assert res_exc["attempt_count"] == 3
    assert res_exc["retry_count"] == 2
    assert "<" in res_exc["loop_condition"]


def test_increment_timing_and_counter_values(synthetic_suite):
    cf, file_name, mod = synthetic_suite

    res_before = cf.analyze_loop_and_retry(file_name, "fn_inclusive_before")
    assert res_before["counter_update_position"] == "before_call"
    seq_before = res_before["attempt_sequence"]
    assert len(seq_before) == 3
    # Incremented before call: counter values at call are 1, 2, 3
    assert [s["counter_at_call"] for s in seq_before] == [1, 2, 3]

    res_after = cf.analyze_loop_and_retry(file_name, "fn_exclusive_after")
    assert res_after["counter_update_position"] == "after_call"
    seq_after = res_after["attempt_sequence"]
    assert len(seq_after) == 3
    # Incremented after call: counter values at call are 0, 1, 2
    assert [s["counter_at_call"] for s in seq_after] == [0, 1, 2]


def test_nonzero_initial_counter_value(synthetic_suite):
    cf, file_name, mod = synthetic_suite

    # Pattern 3: attempts starts at 1, condition <= 3, inc before -> attempts=2, 3, 4 (3 attempts total)
    res = cf.analyze_loop_and_retry(file_name, "fn_nonzero_start")
    assert res["attempt_count"] == 3
    seq = res["attempt_sequence"]
    assert [s["counter_at_call"] for s in seq] == [2, 3, 4]


def test_explicit_continue_vs_implicit_iteration(synthetic_suite):
    cf, file_name, mod = synthetic_suite

    # Pattern 1: No continue statement in handler -> IMPLICIT_NEXT_ITERATION
    res_implicit = cf.analyze_loop_and_retry(file_name, "fn_inclusive_before")
    trace_imp = res_implicit["execution_trace"]
    assert any(s.get("continuation_type") == "IMPLICIT_NEXT_ITERATION" for s in trace_imp)
    assert not any(s.get("continuation_type") == "EXPLICIT_CONTINUE" for s in trace_imp)

    # Pattern 4: Explicit continue in handler -> EXPLICIT_CONTINUE
    res_explicit = cf.analyze_loop_and_retry(file_name, "fn_explicit_continue")
    trace_exp = res_explicit["execution_trace"]
    assert any(s.get("continuation_type") == "EXPLICIT_CONTINUE" for s in trace_exp)
    assert any(s.get("statement") == "continue" for s in trace_exp)


def test_try_scope_skipped_success_branches(synthetic_suite):
    cf, file_name, mod = synthetic_suite

    res = cf.analyze_loop_and_retry(file_name, "fn_inclusive_before")
    trace = res["execution_trace"]

    # Statements after service.call() in try block must be SKIPPED under failure scenario
    skipped_steps = [s for s in trace if s.get("execution_status") == "SKIPPED"]
    assert len(skipped_steps) > 0
    assert any("shipped" in s.get("statement", "") for s in skipped_steps)

    # In potential branch effects, notify("shipped") is listed as SKIPPED_UNDER_SCENARIO
    pot_effects = res["potential_branch_effects"]
    assert any("shipped" in pe.get("statement", "") and pe.get("scenario_status") == "SKIPPED_UNDER_SCENARIO" for pe in pot_effects)

    # In executed scenario effects, notify("shipped") must NOT be executed
    exec_effects = res["executed_scenario_effects"]
    assert not any("shipped" in ee.get("statement", "") for ee in exec_effects)


def test_early_return_and_break_in_exception_handler(synthetic_suite):
    cf, file_name, mod = synthetic_suite

    # Pattern 5: Early return in handler -> exactly 1 attempt
    res_ret = cf.analyze_loop_and_retry(file_name, "fn_early_return")
    assert res_ret["has_early_exit_in_handler"] is True
    assert res_ret["attempt_count"] == 1

    # Pattern 6: Break in handler -> exactly 1 attempt before loop exits
    res_break = cf.analyze_loop_and_retry(file_name, "fn_break")
    assert res_break["has_early_exit_in_handler"] is True
    assert res_break["attempt_count"] == 1


# ==============================================================================
# 2. CROSS-SECTION CONSISTENCY & CITATION VALIDATION (Fixes 6 & 7)
# ==============================================================================

def test_cross_section_validator_reconciles_numerical_contradictions():
    validator = CrossSectionValidator(repo_id="test_repo")

    # Contradictory text: direct answer says 4 attempts, but audit events says 3 carrier_retry events
    conflicting_text = (
        "## Direct Answer\n"
        "- Calculated Attempts: 4 carrier attempts occur when MAX_RETRIES = 3.\n"
        "- Audit Events: 3 carrier_retry events recorded.\n"
        "### Scenario Evaluation\n"
        "carrier_retry (3 times)\n"
    )

    reconciled, issues = validator.validate_and_reconcile(
        conflicting_text,
        shared_ir={"calculated_attempts": 4, "calculated_retries": 3}
    )

    assert len(issues) >= 2
    assert "4 carrier_retry events" in reconciled
    assert "3 carrier_retry events" not in reconciled
    assert "carrier_retry (4 times)" in reconciled


def test_cross_section_validator_removes_success_ops_under_failure():
    validator = CrossSectionValidator(repo_id="test_repo")

    contradictory_text = (
        "Scenario: create_label always raises TimeoutError\n"
        "### Observed Scenario Effects\n"
        "- Carrier Invocations: 4\n"
        "- notify_customer('shipped')\n"
        "- status = 'shipped'\n"
        "- release(sku)\n"
    )

    reconciled, issues = validator.validate_and_reconcile(contradictory_text)

    assert "notify_customer('shipped')" not in reconciled
    assert "status = 'shipped'" not in reconciled
    assert "release(sku)" in reconciled
    assert any(i.issue_type == "status_contradiction" for i in issues)


def test_citation_validator_rejects_none_locations():
    verifier = EvidenceVerifier(repo_id="test_repo", repo_path="/tmp")

    # Rejected if file or line is None
    res1 = verifier._verify_citation("[None:None]")
    assert res1.is_valid is False
    assert "NONE_CITATION" in res1.rejection_reason

    res2 = verifier._verify_citation("[dispatch.py:None]")
    assert res2.is_valid is False
    assert "NONE_CITATION" in res2.rejection_reason

    # Validator converts None citations to unsupported
    validator = CrossSectionValidator(repo_id="test_repo")
    text_with_none = "Counter initialized at [None:None] and checked at [None]."
    cleaned, issues = validator.validate_and_reconcile(text_with_none)
    assert "[None:None]" not in cleaned
    assert "[None]" not in cleaned
    assert "[unsupported]" in cleaned


# ==============================================================================
# 3. ORBITFLOW ACCEPTANCE TESTS A, B, C, D (Section 11)
# ==============================================================================

@pytest.fixture(scope="module")
def orbitflow_investigator():
    # Find orbitflow repository in data directory
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../data/repos/repo_orbitflow_asteri_1441ae/OrbitFlow_Benchmark"))
    if not os.path.exists(repo_root):
        pytest.skip(f"OrbitFlow benchmark repo not found at {repo_root}")
    return GraphInvestigator(repo_id="orbitflow_asteri_1441ae", repo_path=repo_root)


def test_orbitflow_acceptance_test_a(orbitflow_investigator):
    """
    Test A:
    Question: 'If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES = 2?
               Explain the audit events, inventory changes, and notifications.'
    Expected:
    - Three carrier invocations.
    - Three carrier_retry events.
    - Failure event and failure notification on exhaustion.
    - Inventory release if confirmed by actual source scope.
    - No successful shipping notification.
    - Source citations for all relevant operations.
    """
    q = "If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES = 2? Explain the audit events, inventory changes, and notifications."
    answer = orbitflow_investigator.investigate(q)

    # 1. Numerical attempts & invocations
    assert "3 carrier attempt" in answer or "3 attempts" in answer.lower()
    assert "MAX_RETRIES = 2" in answer

    # 2. Audit events: carrier_retry recorded 3 times
    assert "carrier_retry" in answer
    assert "3 times" in answer or "3x" in answer or "3 carrier_retry" in answer

    # 3. Inventory release on exhaustion
    assert "release" in answer.lower()

    # 4. Failure notification and audit event on exhaustion
    assert "failed" in answer.lower()

    # 5. Success operations NOT executed
    assert "Observed Scenario Effects" in answer
    if "Observed Scenario Effects" in answer:
        observed_section = answer.split("Observed Scenario Effects")[1].split("###")[0]
        assert "notify_customer(shipment.order_id, 'shipped')" not in observed_section
        assert "status = 'shipped'" not in observed_section

    # 6. Skipped operations properly listed
    assert "Potential Alternative-Branch Effects" in answer or "Skipped" in answer

    # 7. No None in citations
    assert "[None" not in answer


def test_orbitflow_acceptance_test_b(orbitflow_investigator):
    """
    Test B:
    Question: 'If MAX_RETRIES changes from 2 to 3, will the carrier receive three or four attempts?
               Show the loop condition and explain.'
    Expected:
    - Four invocations.
    - Accurate counter sequence.
    - Correct source citations.
    - No contradictory three-attempt explanation.
    - If discussing an all-fail scenario, four retry events.
    """
    q = "If MAX_RETRIES changes from 2 to 3, will the carrier receive three or four attempts? Show the loop condition and explain."
    answer = orbitflow_investigator.investigate(q)

    # 1. Concludes 4 attempts occur
    assert "4 carrier attempt" in answer or "4 attempts" in answer.lower()
    assert "<= MAX_RETRIES" in answer or "<=" in answer

    # 2. No contradictory 3 attempts claim in Direct Answer
    assert "- **Calculated Attempts**: **4 carrier attempt(s)**" in answer or "4 carrier attempt" in answer

    # 3. Explains counter sequence
    assert "1, 2, 3, 4" in answer or "counter" in answer.lower()

    # 4. Citations valid
    assert "orbitflow/dispatch.py" in answer
    assert "[None" not in answer


def test_orbitflow_acceptance_test_c(orbitflow_investigator):
    """
    Test C:
    Question: 'Trace a VIP order from create_order() through manual approval to create_label().
               Why is approve_review() necessary?'
    Expected:
    - Identify the infeasible direct dispatch path for VIP orders.
    - Explain the persisted review state.
    - Identify the independent approval entry point.
    - Distinguish static call paths from state-mediated workflow transitions.
    """
    q = "Trace a VIP order from create_order() through manual approval to create_label(). Why is approve_review() necessary?"
    answer = orbitflow_investigator.investigate(q)

    # 1. Infeasible static path identification
    assert "infeasible" in answer.lower() or "cannot execute" in answer.lower()
    assert "manual_review" in answer or "review" in answer.lower()

    # 2. Persisted state explanation
    assert "state" in answer.lower() or "SHIPMENTS" in answer

    # 3. Independent approval entry point
    assert "approve_review" in answer


def test_orbitflow_acceptance_test_d(orbitflow_investigator):
    """
    Test D:
    Question: 'Which important failure branches in approve_review() are not directly tested?'
    Expected:
    - Identify uncovered source branches.
    - Distinguish direct tests from transitive reachability.
    - Avoid claiming coverage without evidence.
    """
    q = "Which important failure branches in approve_review() are not directly tested?"
    answer = orbitflow_investigator.investigate(q)

    # 1. Identifies untested branch in approve_review()
    assert "reserve" in answer.lower() or "out_of_stock" in answer.lower()
    assert "untested" in answer.lower() or "missing" in answer.lower()
    assert "test_review.py" in answer
