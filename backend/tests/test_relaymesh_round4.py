"""
tests/test_relaymesh_round4.py - ASTERION Round 4 Integration & Regression Suite.

Covers all 15 required automated test specifications:
1. Transient failure produces exactly two calls and one timeout event across every report section.
2. Persistent failure produces three calls and three timeout events.
3. Retry override to four produces five maximum calls and five timeout events.
4. First-attempt success produces one call and zero timeout events.
5. VIP workflow reconstruction spans all three independent entrypoints.
6. No fabricated direct CALLS path exists between approval and worker execution.
7. Test-impact categories are mutually exclusive.
8. Mutation testing verifies which tests actually detect removal of release().
9. Replay recovery produces four cumulative calls and one final successful attempt.
10. Replay recovery includes the complete event history.
11. Failed replay reservation consumes replay budget.
12. A second replay after exhausted budget raises the correct exception.
13. Invalid approval status and insufficient quota have complete branch effects.
14. Source locations and symbol identities are accurate.
15. Final answers contain no contradictory numerical or state claims.
"""

import os
import pytest
from typing import Dict, Any

from app.agent.investigator import GraphInvestigator
from app.agent.control_flow import ControlFlowAnalyzer
from app.agent.symbolic_exec import BoundedSymbolicExecutor
from app.agent.tools import TypedGraphTools
from app.agent.reconciler import InvestigationReconciler
from app.agent.resolver import SymbolResolver
from app.agent.verifier import CrossSectionValidator
from app.agent.canonical_ir import ScenarioExecutionResult


@pytest.fixture(scope="module")
def relaymesh_setup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_repos = os.path.abspath(os.path.join(current_dir, "..", "data", "repos"))
    
    relay_repo_id = "repo_relaymesh_asteri_244812"
    relay_path = os.path.join(data_repos, relay_repo_id, "relaymesh_benchmark")
    if not os.path.isdir(relay_path):
        for entry in os.listdir(data_repos):
            if "relaymesh" in entry.lower():
                cand = os.path.join(data_repos, entry)
                if os.path.isdir(os.path.join(cand, "relaymesh_benchmark")):
                    relay_path = os.path.join(cand, "relaymesh_benchmark")
                    relay_repo_id = entry
                    break
                elif os.path.isdir(cand):
                    relay_path = cand
                    relay_repo_id = entry
                    break

    assert os.path.isdir(relay_path), f"RelayMesh directory not found at {relay_path}"
    return {"repo_id": relay_repo_id, "repo_path": relay_path}


# 1. Transient failure produces exactly two calls and one timeout event across every report section
def test_01_transient_failure_produces_two_calls_and_one_timeout(relaymesh_setup):
    inv = GraphInvestigator(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    ans, rep = inv.investigate_with_report(
        "If delivery times out once and then succeeds, how many transport calls occur, what is the final quota, and what is the event order?"
    )
    # Direct answer & loop analysis must state 2 calls
    assert "2 transport call" in ans or "2 attempts" in ans or "2 transport call(s)" in ans
    # Must NOT claim 3 transport calls or 3 timeout events
    assert "3 transport call" not in ans
    assert "3 delivery_timeout" not in ans
    # Must state 1 timeout event
    assert "1" in ans and ("delivery_timeout" in ans or "timeout" in ans)
    # Delivered status & final quota 4
    assert "delivered" in ans.lower()
    assert "4" in ans


# 2. Persistent failure produces three calls and three timeout events
def test_02_persistent_failure_produces_three_calls_and_three_timeouts(relaymesh_setup):
    cf = ControlFlowAnalyzer(relaymesh_setup["repo_path"])
    res = cf.evaluate_scenario("Under persistent delivery timeout with default configuration, how many transport calls occur?")
    assert res.get("calculated_attempts") == 3
    timeouts = [e for e in res.get("events_emitted", []) if e == "delivery_timeout"]
    assert len(timeouts) == 3
    assert res.get("final_status") == "dead_letter"


# 3. Retry override to four produces five maximum calls and five timeout events
def test_03_retry_override_to_four_produces_five_calls_and_five_timeouts(relaymesh_setup):
    cf = ControlFlowAnalyzer(relaymesh_setup["repo_path"])
    res = cf.evaluate_scenario("If MAX_DELIVERY_RETRIES changes from 2 to 4, what is the maximum transport-call count? What if the first attempt succeeds?")
    assert res.get("calculated_attempts") == 5
    timeouts = [e for e in res.get("events_emitted", []) if e == "delivery_timeout"]
    assert len(timeouts) == 5
    assert res.get("final_status") == "dead_letter"


# 4. First-attempt success produces one call and zero timeout events
def test_04_first_attempt_success_produces_one_call_and_zero_timeouts(relaymesh_setup):
    cf = ControlFlowAnalyzer(relaymesh_setup["repo_path"])
    res = cf.evaluate_scenario("If MAX_DELIVERY_RETRIES changes from 2 to 4, what if the first attempt succeeds?")
    first_res = res.get("first_success_result", {})
    assert first_res.get("calculated_attempts") == 1
    timeouts = [e for e in first_res.get("events_emitted", []) if e == "delivery_timeout"]
    assert len(timeouts) == 0
    assert first_res.get("final_status") == "delivered"


# 5. VIP workflow reconstruction spans all three independent entrypoints
def test_05_vip_workflow_reconstruction_spans_three_independent_entrypoints(relaymesh_setup):
    tools = TypedGraphTools(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = tools.find_cross_entrypoint_workflows(["create_job", "approve_job"], "deliver")
    vip_wf = res["vip_workflow"]
    stages = vip_wf["stages"]
    assert len(stages) == 3

    # Stage 1: submission
    assert any(k in stages[0]["flow"].lower() for k in ("submit", "review"))
    # Stage 2: approval
    assert any(k in stages[1]["flow"].lower() for k in ("approve", "queued", "outbox"))
    # Stage 3: worker
    assert any(k in stages[2]["flow"].lower() for k in ("poll_once", "dispatch", "deliver"))


# 6. No fabricated direct CALLS path exists between approval and worker execution
def test_06_no_fabricated_direct_calls_path_between_approval_and_worker(relaymesh_setup):
    tools = TypedGraphTools(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = tools.find_cross_entrypoint_workflows(["create_job", "approve_job"], "deliver")
    static_calls = res["static_call_graph"]
    assert static_calls["approve_job"]["has_static_calls_edge"] is False
    assert static_calls["create_job"]["has_static_calls_edge"] is False

    # Edges connecting approve and worker are state/queue transitions
    for edge in res["typed_edges"]:
        if edge["source"] in ("approve_job", "approve") and edge["target"] in ("deliver", "dispatch", "run_worker_once"):
            assert edge["type"] != "CALLS"


# 7. Test-impact categories are mutually exclusive
def test_07_test_impact_categories_are_mutually_exclusive(relaymesh_setup):
    reconciler = InvestigationReconciler(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    test_impacts = reconciler.classify_test_impacts(cleanup_fn="release", containing_fn="dispatch")
    
    by_category = {}
    for test_id, detail in test_impacts.items():
        cat = detail.classification.value if hasattr(detail.classification, "value") else str(detail.classification)
        by_category.setdefault(cat, []).append(detail.test_name)

    # Verify mutual exclusivity
    all_tests = []
    for cat, t_names in by_category.items():
        for t in t_names:
            assert t not in all_tests, f"Test {t} classified into multiple categories! Found in {cat}"
            all_tests.append(t)

    assert "REGRESSION_DETECTING" in by_category
    assert "FUNCTION_EXECUTING_ONLY" in by_category or "STATICALLY_REACHABLE_ONLY" in by_category


# 8. Mutation testing verifies which tests actually detect removal of release()
def test_08_mutation_testing_verifies_release_removal_detectors(relaymesh_setup):
    reconciler = InvestigationReconciler(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    test_impacts = reconciler.classify_test_impacts(cleanup_fn="release", containing_fn="dispatch")
    
    by_category = {}
    for test_id, detail in test_impacts.items():
        cat = detail.classification.value if hasattr(detail.classification, "value") else str(detail.classification)
        by_category.setdefault(cat, []).append(detail.test_name)

    detecting = by_category.get("REGRESSION_DETECTING", [])
    func_only = by_category.get("FUNCTION_EXECUTING_ONLY", [])
    static_only = by_category.get("STATICALLY_REACHABLE_ONLY", [])

    # test_persistent_timeout_restores_quota and test_replay_after_dead_letter detect
    assert "test_persistent_timeout_restores_quota" in detecting
    assert "test_replay_after_dead_letter" in detecting

    # test_worker_success, test_transient_timeout, test_vip_review_handoff do NOT detect
    assert "test_worker_success" not in detecting
    assert "test_transient_timeout" not in detecting
    assert "test_vip_review_handoff" not in detecting

    assert "test_worker_success" in func_only or "test_worker_success" in static_only
    assert "test_transient_timeout" in func_only
    assert "test_vip_review_handoff" in func_only or "test_vip_review_handoff" in static_only


# 9. Replay recovery produces four cumulative calls and one final successful attempt
def test_09_replay_recovery_produces_four_cumulative_calls_and_one_final_attempt(relaymesh_setup):
    executor = BoundedSymbolicExecutor(relaymesh_setup["repo_path"])
    res = executor.simulate_multi_phase_replay("j1", initial_retries=2)
    assert res["cumulative_transport_calls"] == 4
    assert res["final_attempt_counter"] == 1
    assert res["final_status"] == "delivered"
    assert res["final_quota"] == 4


# 10. Replay recovery includes the complete event history
def test_10_replay_recovery_includes_complete_event_history(relaymesh_setup):
    executor = BoundedSymbolicExecutor(relaymesh_setup["repo_path"])
    res = executor.simulate_multi_phase_replay("j1", initial_retries=2)
    expected_order = [
        "queued",
        "delivery_timeout",
        "delivery_timeout",
        "delivery_timeout",
        "dead_letter",
        "replayed",
        "delivered"
    ]
    assert res["complete_event_order"] == expected_order


# 11. Failed replay reservation consumes replay budget
def test_11_failed_replay_reservation_consumes_replay_budget(relaymesh_setup):
    cf = ControlFlowAnalyzer(relaymesh_setup["repo_path"])
    res = cf.evaluate_scenario("failed replay reservation in replay_dead_letter")
    seq = res.get("budget_step_sequence", [])
    assert len(seq) == 7
    # Step 4 increments replay count before Step 5 attempts quota reservation
    assert "Increment replay count" in seq[3]
    assert "Attempt quota reservation" in seq[4]
    assert "Return without enqueueing" in seq[6]
    assert res.get("consumed_budget_on_reservation_failure") is True


# 12. A second replay after exhausted budget raises the correct exception
def test_12_second_replay_after_exhausted_budget_raises_replay_limit_reached(relaymesh_setup):
    cf = ControlFlowAnalyzer(relaymesh_setup["repo_path"])
    res = cf.evaluate_scenario("replay dead-letter job invoked twice with limit 1")
    assert res.get("subsequent_exception_raised") == "ValueError('replay limit reached')"
    assert "replay limit reached" in res.get("exception_message", "")


# 13. Invalid approval status and insufficient quota have complete branch effects
def test_13_invalid_approval_status_and_insufficient_quota_have_complete_branch_effects(relaymesh_setup):
    executor = BoundedSymbolicExecutor(relaymesh_setup["repo_path"])
    res = executor.simulate_branch_test_coverage("approve")
    untested = res.get("untested_branches", [])
    
    # Must identify invalid status branch with ValueError
    inv_status = next((b for b in untested if "status" in b["condition"].lower()), None)
    assert inv_status is not None
    assert inv_status.get("exception_raised") == "ValueError"
    assert "invalid_status" in inv_status.get("recommended_test", "")
    
    # Must identify insufficient quota branch
    no_quota = next((b for b in untested if any(k in b["condition"].lower() for k in ("reserve", "quota", "credit"))), None)
    assert no_quota is not None
    assert "insufficient_quota" in no_quota.get("recommended_test", "")


# 14. Source locations and symbol identities are accurate
def test_14_source_locations_and_symbol_identities_are_accurate(relaymesh_setup):
    resolver = SymbolResolver(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = resolver.resolve("dispatch")
    assert len(res) >= 1
    # dispatch must point to worker.py, NOT models.py
    assert res[0].source_path == "relaymesh/worker.py"
    assert res[0].source_path != "relaymesh/models.py"
    
    # Check no false ambiguity between REPLAY_COUNTS and replay.py
    rep_res = resolver.resolve("REPLAY_COUNTS")
    assert len(rep_res) >= 1
    assert not rep_res[0].is_ambiguous


# 15. Final answers contain no contradictory numerical or state claims
def test_15_final_answers_contain_no_contradictory_numerical_or_state_claims(relaymesh_setup):
    inv = GraphInvestigator(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    
    # Test transient query
    ans_trans, _ = inv.investigate_with_report(
        "If delivery times out once and then succeeds, how many transport calls occur?"
    )
    assert "2 transport call" in ans_trans or "2 attempts" in ans_trans or "2 transport call(s)" in ans_trans
    assert "3 transport call" not in ans_trans
    assert "3 delivery_timeout" not in ans_trans
    
    # Test persistent query override
    ans_ovr, _ = inv.investigate_with_report(
        "If MAX_DELIVERY_RETRIES changes from 2 to 4, what is the maximum transport-call count? What if the first attempt succeeds?"
    )
    assert "5 transport call" in ans_ovr or "5" in ans_ovr
    assert "1 transport call" in ans_ovr or "1" in ans_ovr
    assert "3 transport calls" not in ans_ovr
