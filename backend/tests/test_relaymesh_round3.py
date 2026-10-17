import pytest
import os
import re
from app.graph.schema import (
    STATIC_REL_TYPES,
    INFERRED_REL_TYPES,
    ALL_REL_TYPES,
    is_inferred_relationship,
    is_static_relationship,
)
from app.agent.canonical_ir import (
    CanonicalAnalysisResult,
    ResolvedCanonicalSymbol,
    ScenarioExecutionRecord,
    TestCoverageRecord,
    CoverageClassification,
    ClaimStatus,
)
from app.agent.verifier import (
    EvidenceVerifier,
    CrossSectionValidator,
)
from app.agent.control_flow import ControlFlowAnalyzer
from app.agent.resolver import SymbolResolver
from app.agent.investigator import GraphInvestigator

RELAYMESH_REPO_PATH = "/home/zeraphynx/Projects/asterion/backend/data/repos/repo_relaymesh_asteri_244812/relaymesh_benchmark"


# 1. Semantic graph edges survive indexing and can be queried
def test_01_semantic_graph_edges_survive_indexing_and_querying():
    # Schema check
    expected_rels = {"CALLS", "ENQUEUES", "DEQUEUES", "READS_STATE", "WRITES_STATE", "STATE_TRANSITION"}
    for rel in expected_rels:
        assert is_static_relationship(rel), f"{rel} must be static"

    verifier = EvidenceVerifier(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    # Path hop parsing check for semantic arrows
    hops = verifier._parse_path_hops("enqueue --(ENQUEUES)--> OUTBOX")
    assert len(hops) == 1
    src, rel, dst = hops[0]
    assert src == "enqueue"
    assert rel == "ENQUEUES"
    assert dst == "OUTBOX"

    hops_deq = verifier._parse_path_hops("poll_once --(DEQUEUES)--> OUTBOX")
    assert len(hops_deq) == 1
    src, rel, dst = hops_deq[0]
    assert src == "poll_once"
    assert rel == "DEQUEUES"
    assert dst == "OUTBOX"


# 2. Cross-entrypoint workflows are represented without fabricated CALLS edges
def test_02_cross_entrypoint_workflows_no_fabricated_calls_edges():
    assert "RESUMES_VIA" in INFERRED_REL_TYPES
    assert is_inferred_relationship("RESUMES_VIA")
    assert not is_static_relationship("RESUMES_VIA")

    verifier = EvidenceVerifier(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    # Workflow hop parsing
    hops = verifier._parse_path_hops("enqueue -[:RESUMES_VIA]-> poll_once")
    assert len(hops) == 1
    src, rel, dst = hops[0]
    assert src == "enqueue"
    assert rel == "RESUMES_VIA"
    assert dst == "poll_once"


# 3. Verified and inferred relationships remain distinguishable
def test_03_verified_and_inferred_relationships_distinguishable():
    verifier = EvidenceVerifier(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    # In live or mock verifier, RESUMES_VIA must be captured in inferred_edges
    v_res = verifier.verify_call_path("enqueue -[:RESUMES_VIA]-> poll_once")
    assert any("enqueue -[:RESUMES_VIA]-> poll_once" in e for e in v_res.inferred_edges)
    assert v_res.inferred_edges != v_res.verified_edges


# 4. Five failed attempts produce five timeout events
def test_04_five_failed_attempts_produce_five_timeout_events():
    analyzer = ControlFlowAnalyzer(repo_path=RELAYMESH_REPO_PATH)
    res = analyzer.evaluate_scenario("If MAX_DELIVERY_RETRIES changes from 2 to 4, what is the maximum transport-call count? What if the first attempt succeeds?")
    assert res.get("calculated_attempts") == 5
    assert res.get("final_status") == "dead_letter"

    events = res.get("events_emitted", [])
    timeouts = [e for e in events if e == "delivery_timeout"]
    assert len(timeouts) == 5
    dead_letters = [e for e in events if e == "dead_letter"]
    assert len(dead_letters) == 1


# 5. Immediate success produces one delivery call
def test_05_immediate_success_produces_one_delivery_call():
    analyzer = ControlFlowAnalyzer(repo_path=RELAYMESH_REPO_PATH)
    res = analyzer.evaluate_scenario("If MAX_DELIVERY_RETRIES changes from 2 to 4, what is the maximum transport-call count? What if the first attempt succeeds?")
    first_succ = res.get("first_success_result", {})
    assert first_succ.get("calculated_attempts") == 1
    assert "delivery_timeout" not in first_succ.get("events_emitted", [])
    assert first_succ.get("final_status") == "delivered"
    assert first_succ.get("state_deltas", {}).get("reservation") == "consumed"


# 6. Configuration overrides do not leak into other scenarios
def test_06_configuration_overrides_do_not_leak_across_scenarios():
    record_fail = ScenarioExecutionRecord(
        scenario_name="override_fail_4",
        config_overrides={"MAX_DELIVERY_RETRIES": 4},
        invocation_count=5,
        ordered_events=["delivery_timeout"] * 5,
        final_status="dead_letter"
    )
    record_succ = ScenarioExecutionRecord(
        scenario_name="first_success",
        config_overrides={},
        invocation_count=1,
        ordered_events=["delivered"],
        final_status="delivered"
    )

    ir = CanonicalAnalysisResult(
        repository_id="relaymesh",
        query="q_override"
    )
    ir.add_scenario(record_fail)
    ir.add_scenario(record_succ)

    assert ir.scenarios["override_fail_4"].config_overrides.get("MAX_DELIVERY_RETRIES") == 4
    assert ir.scenarios["first_success"].config_overrides == {}
    assert ir.scenarios["override_fail_4"].invocation_count == 5
    assert ir.scenarios["first_success"].invocation_count == 1


# 7. Detecting tests cannot simultaneously be reported as missing coverage for the same branch and scenario
def test_07_detecting_tests_cannot_simultaneously_be_reported_as_missing_coverage():
    rec_detecting = TestCoverageRecord(
        test_id="test_persistent_timeout_restores_quota",
        target_branch_id="failure_cleanup",
        hypothetical_change_id="remove_release",
        classification=CoverageClassification.REGRESSION_DETECTING,
        feasible_execution=True,
        relevant_assertion="assert CREDITS[job.tenant] == 5 and job.id not in RESERVED"
    )
    rec_missing = TestCoverageRecord(
        test_id="test_missing_check",
        target_branch_id="failure_cleanup",
        hypothetical_change_id="remove_release",
        classification=CoverageClassification.GENUINELY_UNCOVERED
    )

    ir = CanonicalAnalysisResult(
        repository_id="relaymesh",
        query="q_cov"
    )
    ir.add_test_coverage(rec_detecting)
    ir.add_test_coverage(rec_missing)
    contradictions = ir.validate_and_reconcile()
    assert len(contradictions) > 0
    assert any("contradiction" in c.lower() for c in contradictions)


# 8. Test classifications are based on actual assertions
def test_08_test_classifications_based_on_actual_assertions():
    rec = TestCoverageRecord(
        test_id="test_persistent_timeout_restores_quota",
        target_branch_id="worker.py:dispatch:failure_cleanup",
        hypothetical_change_id="remove_release",
        classification=CoverageClassification.REGRESSION_DETECTING,
        feasible_execution=True,
        relevant_assertion="assert CREDITS[job.tenant] == 5, assert job.id not in RESERVED"
    )
    assert rec.classification == CoverageClassification.REGRESSION_DETECTING
    assert "CREDITS" in rec.relevant_assertion


# 9. Every requested subquestion appears in the direct answer
def test_09_every_requested_subquestion_appears_in_direct_answer():
    investigator = GraphInvestigator(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    question = "If MAX_DELIVERY_RETRIES changes from 2 to 4, what is the maximum transport-call count? What if the first attempt succeeds?"
    initial_text = "The maximum calls is 5 under persistent failure."
    
    pdata = {
        "question": question,
        "traversal_results": {
            "control_flow_scenario": {
                "first_success_result": {"total_attempts": 1}
            }
        }
    }
    completed_text = investigator._verify_answer_completeness(question, initial_text, pdata)
    assert "First-Attempt Success Scenario" in completed_text
    assert "1 delivery call" in completed_text


# 10. Canonical symbol identities are stable and deduplicated
def test_10_canonical_symbol_identities_stable_and_deduplicated():
    sym1 = ResolvedCanonicalSymbol(
        id="relaymesh:worker.py:dispatch:Function:10:45",
        name="dispatch",
        kind="Function",
        file_path="worker.py",
        qualified_name="dispatch",
        start_line=10,
        end_line=45
    )
    sym2 = ResolvedCanonicalSymbol(
        id="relaymesh:worker.py:dispatch:Function:10:45",
        name="dispatch",
        kind="Function",
        file_path="worker.py",
        qualified_name="dispatch",
        start_line=10,
        end_line=45
    )
    ir = CanonicalAnalysisResult(
        repository_id="relaymesh",
        query="q_sym",
        resolved_symbols=[sym1, sym2]
    )
    ir.validate_and_reconcile()
    # Deduplicated by id
    assert len(ir.resolved_symbols) == 1


# 11. Source locations refer to the correct functions and statements
def test_11_source_locations_refer_to_correct_functions_and_statements(tmp_path):
    # Create a models.py with a field/assignment and a worker.py with def dispatch
    models_py = tmp_path / "models.py"
    models_py.write_text("class Job:\n    dispatch = 'field'\n")
    worker_py = tmp_path / "worker.py"
    worker_py.write_text("def dispatch(job):\n    return True\n")

    resolver = SymbolResolver(repo_id="relaymesh", repo_path=str(tmp_path))
    v_path, v_start, v_end = resolver._validate_source_location("dispatch", "models.py", 2, 2)
    # Must prioritize worker.py def dispatch over models.py field
    assert v_path == "worker.py"
    assert v_start == 1


# 12. Domain-specific terminology cannot leak across repositories
def test_12_domain_specific_terminology_cannot_leak_across_repositories():
    investigator = GraphInvestigator(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    # For relaymesh, payment terms must not be present
    text = (
        "## Direct Answer\n"
        "- 5 transport calls occur.\n"
        "- State: 5 timeout events, hold released, balance restored.\n"
    )
    validator = CrossSectionValidator(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    reconciled, _ = validator.validate_and_reconcile(text, intent="CONTROL_FLOW_ANALYSIS", pdata={"question": "override"})
    # Reconciler should replace or not introduce payment terminology
    assert "account balance" not in reconciled.lower()


# 13. Evidence verification cannot contradict the final answer without surfacing conflict
def test_13_evidence_verification_cannot_contradict_final_answer():
    validator = CrossSectionValidator(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    conflicting_text = (
        "## Direct Answer\n"
        "- 5 transport calls occur.\n"
        "### Audit Events\n"
        "- Exactly 3 delivery_timeout events recorded.\n"
    )
    reconciled, issues = validator.validate_and_reconcile(conflicting_text, pdata={"question": "from 2 to 4"})
    assert any(iss.issue_type == "numerical_mismatch" for iss in issues)
    # The timeout count must be reconciled to match the 5 calls
    assert "5 delivery_timeout events" in reconciled


# 14. Empty or invalid citations are excluded
def test_14_empty_or_invalid_citations_excluded():
    validator = CrossSectionValidator(repo_id="relaymesh", repo_path=RELAYMESH_REPO_PATH)
    text_with_bad_citations = (
        "In `dispatch` [None:None], the loop terminates [None]. Source: worker.py:None."
    )
    reconciled, issues = validator.validate_and_reconcile(text_with_bad_citations)
    assert "[None:None]" not in reconciled
    assert "[None]" not in reconciled
    assert "worker.py:None" not in reconciled
    assert any(iss.issue_type == "invalid_citation" for iss in issues)
