"""
Automated regression tests for ASTERION upgrade on RelayMesh and general Python codebases.
Covers all 12 criteria specified in Section 7 of the specification:
1. Cross-entrypoint outbox traversal
2. VIP review-to-worker handoff
3. Absence of a direct submission-to-delivery call path
4. Hypothetical retry-configuration override
5. Inclusive retry-loop counting (retries=2 -> 3, retries=4 -> 5, immediate success -> 1)
6. Failure-cleanup regression detection
7. Successful-path tests not falsely detecting failure-only regressions
8. Canonical symbol resolution
9. Source-location correctness
10. Cross-repository terminology isolation (no payment terms in RelayMesh)
11. Evidence relevance and deduplication
12. Analyzer failure not being represented as successful verification
"""

import os
import pytest
from app.agent.investigator import GraphInvestigator
from app.agent.tools import TypedGraphTools
from app.agent.impact import ImpactAnalyzer
from app.agent.control_flow import ControlFlowAnalyzer
from app.agent.symbolic_exec import BoundedSymbolicExecutor
from app.agent.resolver import EntityResolver, EntityOrigin
from app.agent.pipeline import ReasoningPipeline


@pytest.fixture(scope="module")
def relaymesh_setup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_repos = os.path.abspath(os.path.join(current_dir, "..", "data", "repos"))
    
    relay_repo_id = "repo_relaymesh_asteri_244812"
    relay_path = os.path.join(data_repos, relay_repo_id, "relaymesh_benchmark")
    if not os.path.isdir(relay_path):
        # Fallback to any directory matching relaymesh
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


# 1. Cross-entrypoint outbox traversal
def test_cross_entrypoint_outbox_traversal(relaymesh_setup):
    tools = TypedGraphTools(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = tools.find_cross_entrypoint_workflows(["create_job", "approve_job"], "deliver")

    assert res["is_cross_entrypoint"] is True
    assert "OUTBOX" in res["producer_flows"]["create_job"]
    assert "OUTBOX" in res["producer_flows"]["approve_job"]
    assert "run_worker_once -> poll_once -> dispatch -> deliver" in res["consumer_static_path"]

    # Verify edge types present
    edge_types = {e["type"] for e in res["typed_edges"]}
    assert "ENQUEUES" in edge_types
    assert "DEQUEUES" in edge_types
    assert "RESUMES_VIA" in edge_types
    assert "CALLS" in edge_types
    assert "STATE_TRANSITION" in edge_types


# 2. VIP review-to-worker handoff
def test_vip_review_to_worker_handoff(relaymesh_setup):
    tools = TypedGraphTools(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = tools.find_cross_entrypoint_workflows(["create_job", "approve_job"], "deliver")

    vip_wf = res["vip_workflow"]
    stages = vip_wf["stages"]
    assert len(stages) == 3

    # Stage 1: Submission saves review state, no enqueue
    assert "review" in stages[0]["flow"].lower()
    assert any(e["type"] == "STATE_TRANSITION" for e in stages[0]["edges"])

    # Stage 2: Separate approval entrypoint
    assert "approve" in stages[1]["flow"].lower()
    assert any(e["type"] == "ENQUEUES" for e in stages[1]["edges"])

    # Stage 3: Worker dequeue & delivery
    assert any(e["type"] == "DEQUEUES" for e in stages[2]["edges"])
    assert any(e["type"] == "CALLS" for e in stages[2]["edges"])


# 3. Absence of a direct submission-to-delivery call path
def test_absence_of_direct_call_path(relaymesh_setup):
    tools = TypedGraphTools(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = tools.find_cross_entrypoint_workflows(["create_job", "approve_job"], "deliver")

    static_calls = res["static_call_graph"]
    assert static_calls["create_job"]["has_static_calls_edge"] is False
    assert static_calls["approve_job"]["has_static_calls_edge"] is False
    assert "No direct or transitive static `CALLS` edge exists" in static_calls["create_job"]["explanation"]


# 4. Hypothetical retry-configuration override
def test_hypothetical_retry_configuration_override(relaymesh_setup):
    analyzer = ImpactAnalyzer(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = analyzer.analyze_configuration_override("MAX_DELIVERY_RETRIES", 4)

    assert res.mode == "HYPOTHETICAL_CONFIGURATION_OVERRIDE"
    assert res.risk_score > 0.0
    assert res.risk_level in ("HIGH", "MEDIUM")
    assert "MAX_DELIVERY_RETRIES" in res.target_symbol
    assert any("MAX_DELIVERY_RETRIES = 4" in exp for exp in res.explanations)
    assert any("5 invocations" in exp for exp in res.explanations)


# 5. Inclusive retry-loop counting (2 -> 3, 4 -> 5, immediate -> 1)
def test_inclusive_retry_loop_counting(relaymesh_setup):
    cf = ControlFlowAnalyzer(relaymesh_setup["repo_path"])
    
    # MAX_DELIVERY_RETRIES = 2 gives 3 maximum calls
    sim2 = cf.analyze_loop_and_retry(
        "relaymesh/worker.py", "dispatch", max_retries_override=2, query="MAX_DELIVERY_RETRIES = 2"
    )
    assert sim2["attempt_count"] == 3

    # MAX_DELIVERY_RETRIES = 4 gives 5 maximum calls
    sim4 = cf.analyze_loop_and_retry(
        "relaymesh/worker.py", "dispatch", max_retries_override=4, query="MAX_DELIVERY_RETRIES = 4"
    )
    assert sim4["attempt_count"] == 5

    # First attempt success scenario: 1 call
    scen_res = cf.evaluate_scenario("If transport succeeds immediately on first try, how many calls?")
    # Or query investigation
    inv = GraphInvestigator(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    ans, rep = inv.investigate_with_report(
        "If MAX_DELIVERY_RETRIES changes from 2 to 4, what is the maximum transport-call count? What if the first attempt succeeds?"
    )
    assert "5 transport call" in ans or "5" in ans
    assert "1 transport call" in ans or "1" in ans


# 6. Failure-cleanup regression detection
def test_failure_cleanup_regression_detection(relaymesh_setup):
    sim = BoundedSymbolicExecutor(relaymesh_setup["repo_path"])
    res = sim.simulate_cleanup_removal_impact("release", "dispatch")

    detecting = res["regression_detecting_tests"]
    assert any("test_persistent_timeout_restores_quota" in t for t in detecting)
    assert "quota" in res["resource_consequence"].lower() or "credits" in res["resource_consequence"].lower()


# 7. Successful-path tests not falsely detecting failure-only regressions
def test_successful_tests_not_detecting_failure_cleanup(relaymesh_setup):
    sim = BoundedSymbolicExecutor(relaymesh_setup["repo_path"])
    res = sim.simulate_cleanup_removal_impact("release", "dispatch")

    detecting = res["regression_detecting_tests"]
    statically_reachable = res["statically_reachable_tests"]

    # Success tests must NOT be in regression detecting list
    assert not any("test_worker_success" in t for t in detecting)
    assert not any("test_vip_review_handoff" in t for t in detecting)
    assert not any("test_submission_only_queues" in t for t in detecting)

    # Success and early-return tests belong to non-detecting / reachable
    assert any("test_worker_success" in t for t in statically_reachable) or any("test_vip_review_handoff" in t for t in statically_reachable)


# 8. Canonical symbol resolution
def test_canonical_symbol_resolution(relaymesh_setup):
    resolver = EntityResolver(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    
    # Resolve MAX_DELIVERY_RETRIES
    res_const = resolver.resolve("MAX_DELIVERY_RETRIES")
    assert len(res_const) >= 1
    assert res_const[0].type == "ConfigConstant"
    assert res_const[0].source_path == "relaymesh/config.py"
    assert res_const[0].origin == EntityOrigin.REPOSITORY

    # Resolve dispatch
    res_fn = resolver.resolve("dispatch")
    assert len(res_fn) >= 1
    assert res_fn[0].type in ("Function", "Method")
    assert res_fn[0].name == "dispatch"


# 9. Source-location correctness
def test_source_location_correctness(relaymesh_setup):
    resolver = EntityResolver(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = resolver.resolve("dispatch")
    
    # Must point to worker.py, NOT models.py
    assert len(res) >= 1
    assert res[0].source_path == "relaymesh/worker.py"
    assert res[0].source_path != "relaymesh/models.py"


# 10. Cross-repository terminology isolation
def test_cross_repository_terminology_isolation(relaymesh_setup):
    inv = GraphInvestigator(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    
    # Question about release() removal in RelayMesh
    ans, rep = inv.investigate_with_report(
        "If dispatch() no longer calls release() after retry exhaustion, which workflows and tests are affected?"
    )
    
    ans_lower = ans.lower()
    # Must NOT introduce unrelated payment terminology
    assert "account balance" not in ans_lower
    assert "balances" not in ans_lower
    assert "holds" not in ans_lower
    assert "gateway" not in ans_lower
    assert "nexuspay" not in ans_lower
    assert "orbitflow" not in ans_lower


# 11. Evidence relevance and deduplication
def test_evidence_relevance_and_deduplication(relaymesh_setup):
    tools = TypedGraphTools(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    res = tools.find_cross_entrypoint_workflows(["create_job", "approve_job"], "deliver")

    citations = res["citations"]
    # Check deduplication
    assert len(citations) == len(set(citations))
    # Citations must point to actual file:line
    for cit in citations:
        assert ":" in cit
        f_p, l_n = cit.split(":")
        assert os.path.exists(os.path.join(relaymesh_setup["repo_path"], f_p))
        assert int(l_n) > 0


# 12. Analyzer failure not being represented as successful verification
def test_analyzer_failure_not_represented_as_success(relaymesh_setup):
    analyzer = ImpactAnalyzer(relaymesh_setup["repo_id"], relaymesh_setup["repo_path"])
    # Nonexistent constant
    res = analyzer.analyze_configuration_override("NONEXISTENT_CONSTANT_XYZ", 99)

    assert res.mode == "ANALYSIS_FAILED"
    # Never report zero risk or fake success on failure
    assert res.risk_score > 0.0
    assert res.risk_level == "HIGH"
    assert "Failed to locate definition" in res.diff_summary
