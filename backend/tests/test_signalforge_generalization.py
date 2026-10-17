"""
tests/test_signalforge_generalization.py - SignalForge Generalization & Cross-Repository Isolation Suite.

Validates the full generalization of ASTERION to SignalForge without RelayMesh cross-contamination,
verifying dynamic extraction from AST, 12 capabilities intent classification, procedural vs factual
memory separation, state ledger completeness, and hard-gate verification across all 16 scenarios:
1. Repository isolation & symbol quarantine (RelayMesh markers flagged as alien in SignalForge).
2. Procedural memory reuse without factual leakage.
3. Multi-label intent classification across 12 capabilities.
4. State ledger completeness (6 phases, cumulative send calls, tokens, events).
5. Critical-team workflow reconstruction (state-mediated handoff create -> review -> approve -> worker).
6. Severity 9 routing (review required, no immediate reservation or enqueue).
7. Muted service sandbox (not saved, not queued, get raises KeyError).
8. Zero tokens at creation (emits budget_denied, not saved/queued).
9. Persistent and transient retries (calls, timeouts, notices, tokens).
10. Retry override to 4 (5 persistent calls, 1 immediate success call).
11. Reopen budget consumption and reopen twice limit (ValueError).
12. Reopened incident permanent failure (6 calls, 6 timeouts, 2 failed events).
13. Mutation impact & detecting tests (removal of release() classified correctly).
14. Queue producers, consumers, and scheduler absence.
15. Crash window after pop before dispatch (destructive pop creates loss window).
16. Hard-gate verification seal (fabricated paths stripped from Verified Graph Relationships).
"""

import os
import re
import pytest
from typing import Dict, Any

from app.agent.context import InvestigationContext
from app.agent.intent import IntentClassifier
from app.agent.investigator import GraphInvestigator
from app.agent.control_flow import ControlFlowAnalyzer
from app.agent.symbolic_exec import BoundedSymbolicExecutor, ExecutionLedger
from app.agent.tools import TypedGraphTools
from app.agent.reconciler import InvestigationReconciler
from app.agent.resolver import SymbolResolver
from app.agent.verifier import CrossSectionValidator, VerificationReport, PathVerification


@pytest.fixture(scope="module")
def signalforge_setup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    data_repos = os.path.abspath(os.path.join(current_dir, "..", "data", "repos"))
    
    sf_repo_id = "repo_signalforge_aste_d53975"
    sf_path = os.path.join(data_repos, sf_repo_id, "SignalForge_ASTERION_Benchmark_3")
    if not os.path.isdir(sf_path):
        for entry in os.listdir(data_repos):
            if "signalforge" in entry.lower():
                cand = os.path.join(data_repos, entry)
                if os.path.isdir(os.path.join(cand, "SignalForge_ASTERION_Benchmark_3")):
                    sf_path = os.path.join(cand, "SignalForge_ASTERION_Benchmark_3")
                    sf_repo_id = entry
                    break
                elif os.path.isdir(cand):
                    sf_path = cand
                    sf_repo_id = entry
                    break

    assert os.path.isdir(sf_path), f"SignalForge directory not found at {sf_path}"
    return {"repo_id": sf_repo_id, "repo_path": sf_path}


# 1. Repository Isolation & Symbol Quarantine
def test_repository_isolation_and_symbol_quarantine(signalforge_setup):
    repo_id = signalforge_setup["repo_id"]
    repo_path = signalforge_setup["repo_path"]
    ctx = InvestigationContext(repository_id=repo_id, repository_path=repo_path)

    # RelayMesh markers must be alien to SignalForge
    assert ctx.is_alien_symbol("create_job")
    assert ctx.is_alien_symbol("approve_job")
    assert ctx.is_alien_symbol("submit")
    assert ctx.is_alien_symbol("OUTBOX")
    assert ctx.is_alien_symbol("JOBS")
    assert ctx.is_alien_symbol("CREDITS")
    assert ctx.is_alien_symbol("dead_letter")
    assert ctx.is_alien_symbol("deliver")

    # SignalForge symbols must NOT be alien to SignalForge
    assert not ctx.is_alien_symbol("create_incident")
    assert not ctx.is_alien_symbol("approve_incident")
    assert not ctx.is_alien_symbol("QUEUE")
    assert not ctx.is_alien_symbol("INCIDENTS")
    assert not ctx.is_alien_symbol("TOKENS")
    assert not ctx.is_alien_symbol("send")

    # Text consistency validation must catch foreign symbols
    valid, errors = ctx.validate_repository_consistency("We execute create_job() to enqueue into OUTBOX.")
    assert not valid
    assert any("create_job" in e or "OUTBOX" in e for e in errors)

    # Quarantine must sanitize foreign symbols
    quarantined = ctx.quarantine_contaminated_text("We execute create_job() to enqueue into OUTBOX.")
    assert "create_job" not in quarantined or "[QUARANTINED]" in quarantined
    assert "OUTBOX" not in quarantined or "[QUARANTINED]" in quarantined


# 2. Procedural Memory Reuse Without Factual Leakage
def test_procedural_memory_reuse_without_factual_leakage(signalforge_setup):
    repo_id = signalforge_setup["repo_id"]
    repo_path = signalforge_setup["repo_path"]
    validator = CrossSectionValidator(repo_id=repo_id, repo_path=repo_path)

    contaminated_text = (
        "## Direct Answer\n"
        "- Status: Final status is 'dead_letter'.\n"
        "- Enqueued into OUTBOX and decrements CREDITS.\n"
        "- deliver() is called by run_worker_once()."
    )
    reconciled, issues = validator.validate_and_reconcile(contaminated_text)
    assert "OUTBOX" not in reconciled
    assert "CREDITS" not in reconciled
    assert "dead_letter" not in reconciled
    assert "QUEUE" in reconciled
    assert "TOKENS" in reconciled
    assert "failed" in reconciled


# 3. Multi-label Intent Classification across 12 Capabilities
def test_intent_classification_multilabel_12_capabilities():
    classifier = IntentClassifier()

    q_map = [
        ("Enumerate static CALLS paths from create_incident() to send()", "STATIC_PATH_ANALYSIS"),
        ("After normal create_incident() returns, has send() run? Give status, tokens", "STATE_EFFECT_QUERY"),
        ("Trace a critical-team incident through creation, approval and worker polling", "CROSS_ENTRYPOINT_WORKFLOW"),
        ("Does a normal-team severity-9 incident bypass review or reserve a token immediately?", "BRANCH_CONDITION_ANALYSIS"),
        ("With MAX_SEND_RETRIES=2 and persistent timeout, how many send calls and timeout events occur?", "LOOP_EXECUTION_ANALYSIS"),
        ("Change MAX_SEND_RETRIES from 2 to 4. Give maximum calls under persistent failure", "CONFIGURATION_OVERRIDE"),
        ("Remove release() from exhausted dispatch(). Which tests actually detect the regression?", "CHANGE_IMPACT_ANALYSIS"),
        ("Which approve() failure branches lack direct test coverage?", "BRANCH_TEST_COVERAGE"),
        ("After failed incident reopening and transport recovery, give attempts and cumulative send calls", "MULTIPHASE_SCENARIO"),
        ("Can a failed reserve() in reopen_failed() consume reopening budget without enqueueing?", "RESOURCE_BUDGET_ANALYSIS"),
        ("Identify all QUEUE producers and consumers. Is there an automatic scheduler?", "QUEUE_PRODUCER_CONSUMER_ANALYSIS"),
        ("If worker crashes after QUEUE.pop(0) before dispatch(), can queue entry be lost?", "CRASH_CONSISTENCY"),
    ]

    for question, expected_cap in q_map:
        res = classifier.classify(question)
        assert res.has_capability(expected_cap), f"Expected {expected_cap} in capabilities for question: '{question}', got {res.capabilities}"


# 4. State Ledger Completeness (Multiphase Replay)
def test_state_ledger_completeness_multiphase_replay(signalforge_setup):
    executor = BoundedSymbolicExecutor(repo_path=signalforge_setup["repo_path"])
    replay_result = executor.simulate_multi_phase_replay()

    assert replay_result.get("cumulative_send_calls") == 4
    assert replay_result.get("final_attempts") == 1
    assert replay_result.get("final_tokens", {}).get("normal") == 2
    assert replay_result.get("reservation_cleared") is True
    assert replay_result.get("final_status") == "sent"

    expected_events = ["queued", "send_timeout", "send_timeout", "send_timeout", "failed", "reopened", "sent"]
    assert replay_result.get("event_sequence") == expected_events

    # Verify structured ledger contains all 6 phases
    ledger = replay_result.get("ledger")
    assert isinstance(ledger, list) and len(ledger) >= 6
    phase_names = [p.get("phase_name", "").lower() for p in ledger]
    assert any("creation" in p for p in phase_names)
    assert any("failure" in p for p in phase_names)
    assert any("cleanup" in p for p in phase_names)
    assert any("reopen" in p for p in phase_names)
    assert any("polling" in p for p in phase_names)
    assert any("recovery" in p for p in phase_names)


# 5. Critical-Team Workflow Reconstruction (State-Mediated Handoff)
def test_critical_team_workflow_state_mediated_handoff(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    feas = cfa.analyze_path_feasibility(
        source_function="create_incident",
        target_function="send",
        query="Trace a critical-team incident through creation, approval and worker polling",
        shared_ir=None
    )
    assert not feas.is_feasible  # Direct static call is not feasible
    assert feas.state_mediated_workflow is not None
    assert "INCIDENTS" in feas.state_mediated_workflow.get("intermediate_state", "")
    assert "QUEUE" in str(feas.state_mediated_workflow)
    assert "approve" in str(feas.state_mediated_workflow)
    assert "run_worker_once" in str(feas.state_mediated_workflow)
    # Check zero RelayMesh contamination
    assert "create_job" not in str(feas.state_mediated_workflow)
    assert "OUTBOX" not in str(feas.state_mediated_workflow)
    assert "deliver" not in str(feas.state_mediated_workflow)


# 6. Severity 9 Routing Scenario
def test_severity_9_routing_scenario(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    scen = cfa.evaluate_control_flow_scenario(
        question="Does a normal-team severity-9 incident bypass review or reserve a token immediately?"
    )
    assert scen.get("scenario") == "severity_9_routing"
    assert scen.get("bypasses_review") is False
    assert scen.get("reserves_immediately") is False
    assert "review" in scen.get("summary", "").lower()


# 7. Muted Service Sandbox Scenario
def test_muted_service_sandbox_scenario(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    scen = cfa.evaluate_control_flow_scenario(
        question="For service sandbox, is the incident saved or queued? What does get_incident() do?"
    )
    assert scen.get("scenario") == "muted_service_submission"
    assert scen.get("is_saved") is False
    assert scen.get("is_queued") is False
    assert scen.get("get_incident_outcome") == "Raises KeyError"
    assert scen.get("events") == ["muted"]


# 8. Zero Tokens at Creation Scenario
def test_zero_tokens_at_creation_scenario(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    scen = cfa.evaluate_control_flow_scenario(
        question="With normal tokens zero at creation, what is emitted, saved, queued or notified?"
    )
    assert scen.get("scenario") == "zero_tokens_submission"
    assert scen.get("is_persisted") is False
    assert scen.get("tokens_normal") == 0
    assert any("budget_denied" in act for act in scen.get("actions_happened", []))
    assert any("not persisted" in act for act in scen.get("actions_not_happened", []))


# 9. Persistent and Transient Retries
def test_persistent_and_transient_retries(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    res = cfa.evaluate_scenario("With MAX_SEND_RETRIES=2 and persistent timeout, how many send calls and timeout events occur?")
    assert res.get("calculated_attempts") == 3
    timeouts = [e for e in res.get("events_emitted", []) if e == "send_timeout"]
    assert len(timeouts) == 3
    assert res.get("final_status") == "failed"


# 10. Retry Override to 4
def test_retry_override_to_4(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    scen = cfa.evaluate_control_flow_scenario(
        question="Change MAX_SEND_RETRIES from 2 to 4. Give maximum calls under persistent failure and first success"
    )
    assert "retry_semantics" in scen.get("scenario", "")
    assert scen.get("calculated_attempts") == 5
    first_succ = scen.get("first_success_result", {})
    assert first_succ.get("calculated_attempts") == 1
    assert first_succ.get("final_status") == "sent"


# 11. Reopen Budget Consumption and Reopen Limit
def test_reopen_budget_consumption_and_limit(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    
    # Budget consumption test
    scen_cons = cfa.evaluate_control_flow_scenario(
        question="Can a failed reserve() in reopen_failed() consume reopening budget without enqueueing?"
    )
    assert scen_cons.get("scenario") == "reopen_budget_bug"
    assert scen_cons.get("consumed_budget_on_reservation_failure") is True
    assert scen_cons.get("budget_consumed_without_enqueue") is True
    assert scen_cons.get("quota_failure_enqueues") is False

    # Limit test
    scen_lim = cfa.evaluate_control_flow_scenario(
        question="What happens if a failed incident is reopened twice? Explain MAX_REOPEN"
    )
    assert scen_lim.get("scenario") == "reopen_limit_exception"
    assert scen_lim.get("exception_raised") == "ValueError('reopen limit reached')"
    assert "reopen limit reached" in scen_lim.get("exception_message", "")


# 12. Reopened Incident Permanent Failure
def test_reopened_incident_permanent_failure(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    scen = cfa.evaluate_control_flow_scenario(
        question="If a reopened incident exhausts retries again, give cumulative send calls, timeout events, final state and tokens."
    )
    assert scen.get("scenario") == "reopened_permanent_failure"
    assert scen.get("cumulative_send_calls") == 6
    assert scen.get("total_send_timeout_events") == 6
    assert scen.get("total_failed_events") == 2
    assert scen.get("final_status") == "failed"
    assert scen.get("final_tokens", {}).get("normal") == 3
    assert scen.get("reservation_cleared") is True


# 13. Mutation Impact on Removal of release()
def test_mutation_impact_removal_of_release(signalforge_setup):
    executor = BoundedSymbolicExecutor(repo_path=signalforge_setup["repo_path"])
    impact = executor.simulate_cleanup_removal_impact(
        target_function="dispatch",
        cleanup_call="release"
    )
    assert impact.get("cleanups_removed") == ["release"]
    detecting = impact.get("detecting_tests", [])
    assert any("persistent_failure" in t or "reopen" in t for t in detecting)
    # Ensure test classification categories are mutually exclusive
    skipping = impact.get("branch_skipping_tests", [])
    assert set(detecting).isdisjoint(set(skipping))


# 14. Queue Producers, Consumers, and Scheduler Absence
def test_queue_producers_consumers_and_scheduler_absence(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    scen = cfa.evaluate_control_flow_scenario(
        question="Identify all QUEUE producers and consumers. Is there an automatic scheduler?"
    )
    assert scen.get("scenario") == "scheduler_absence_analysis"
    producers = scen.get("producers", [])
    assert "open_incident" in producers
    assert "approve" in producers
    assert "reopen_failed" in producers
    consumers = scen.get("consumers", [])
    assert "poll_once" in consumers
    assert scen.get("runs_automatically") is False
    assert scen.get("automatic_scheduler_present") is False


# 15. Crash Window after pop(0) before dispatch
def test_crash_window_after_pop_before_dispatch(signalforge_setup):
    cfa = ControlFlowAnalyzer(repo_path=signalforge_setup["repo_path"])
    scen = cfa.evaluate_control_flow_scenario(
        question="If worker crashes after QUEUE.pop(0) before dispatch(), can queue entry be lost?"
    )
    assert scen.get("scenario") == "crash_window"
    assert scen.get("lost_from_queue") is True
    assert "signalforge/consumer.py:7" in scen.get("destructive_pop_line", "")
    assert "signalforge/consumer.py:11" in scen.get("dispatch_line", "")


# 16. Hard-Gate Verification Seal
def test_hard_gate_verification_seal(signalforge_setup):
    investigator = GraphInvestigator(
        repo_id=signalforge_setup["repo_id"],
        repo_path=signalforge_setup["repo_path"]
    )
    fake_path = "create_incident -> send"
    report = VerificationReport(
        is_verified=False,
        citations_checked=1,
        citations_valid=1,
        paths_checked=1,
        paths_valid=0,
        fabricated_paths=[PathVerification(raw_path=fake_path, segments=["create_incident", "send"], is_valid=False, rejection_reason="No direct call exists")]
    )
    response_text = (
        "## Summary\n"
        "Here is the workflow.\n\n"
        "### Verified Graph Relationships\n"
        f"- `{fake_path}`\n\n"
        "Done."
    )
    sealed = investigator._apply_verification_seal(
        response_text=response_text,
        report=report,
        pdata={"question": "Test question"}
    )
    # The fabricated path must NOT appear in the sealed text
    assert f"- `{fake_path}`" not in sealed
    assert "### Verified Graph Relationships" not in sealed
    # CAUTION rejection alert must be attached
    assert "Verification Rejection Alert" in sealed
    assert fake_path in sealed
