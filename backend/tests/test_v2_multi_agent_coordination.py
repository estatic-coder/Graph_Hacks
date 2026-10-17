"""
tests/test_v2_multi_agent_coordination.py - Multi-Agent Investigation & Coordination Suite.

Validates:
1. Four specialized roles (Graph Investigator, Execution Analyst, Test Analyst, Evidence Reviewer).
2. Shared FalkorDB investigation state with bounded task claims/leases.
3. Explicit agent handoff records (HANDOFF_TO).
4. Cross-session continuity: Second agent continues investigation started by first.
"""

import os
import pytest

from app.agent.multi_agent import (
    MultiAgentInvestigationCoordinator,
    AgentRole,
    TaskStatus
)


@pytest.fixture(scope="module")
def sf_setup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sf_path = os.path.abspath(os.path.join(
        current_dir, "..", "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3"
    ))
    return {"repo_id": "repo_signalforge_aste_d53975", "repo_path": sf_path}


def test_four_specialized_roles_collaborative_investigation(sf_setup):
    """Verifies end-to-end multi-agent pipeline across all 4 specialized roles."""
    coord = MultiAgentInvestigationCoordinator(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="ws_multiagent"
    )

    res = coord.execute_collaborative_investigation(
        objective="Investigate notification dispatch resilience",
        target_symbol="dispatch",
        scenario_question="With MAX_SEND_RETRIES=2 and persistent timeout, how many send calls occur?"
    )

    assert res["investigation_id"] != ""
    assert res["completed_tasks"] == 4
    assert res["handoff_count"] == 3
    assert res["final_approved"] is True

    # Check findings from each role
    assert res["graph_findings"]["role"] == AgentRole.GRAPH_INVESTIGATOR.value
    assert res["execution_findings"]["role"] == AgentRole.EXECUTION_ANALYST.value
    assert res["test_findings"]["role"] == AgentRole.TEST_IMPACT_ANALYST.value
    assert res["reviewer_result"]["role"] == AgentRole.EVIDENCE_REVIEWER.value
    assert res["reviewer_result"]["decision"] == "APPROVED"


def test_task_claiming_and_concurrency_control(sf_setup):
    """Verifies bounded task lease prevents conflicting agent updates."""
    coord = MultiAgentInvestigationCoordinator(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"]
    )
    inv = coord.start_investigation("Concurrency control test")
    t1 = inv.add_task("task_001", "Perform symbol analysis", AgentRole.GRAPH_INVESTIGATOR)

    # Agent 1 claims task with 10s lease
    assert inv.claim_task("task_001", agent_id="agent_alpha", lease_duration_sec=10.0) is True

    # Agent 2 attempts to claim same task concurrently: must be rejected!
    assert inv.claim_task("task_001", agent_id="agent_beta") is False

    # Complete task
    inv.complete_task("task_001", {"status": "DONE"})
    assert inv.tasks["task_001"]["status"] == TaskStatus.COMPLETED.value


def test_cross_session_investigation_continuation(sf_setup):
    """
    Demonstrates session continuity:
    Agent 1 (Graph Investigator) starts an investigation in Session 1 and records findings.
    Session 1 ends.
    Agent 2 (Test Analyst) resumes the investigation in Session 2 and continues the workflow.
    """
    coord1 = MultiAgentInvestigationCoordinator(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="ws_continuity"
    )
    inv1 = coord1.start_investigation("Trace dispatch dependencies and test coverage", investigation_id="inv_shared_continuity")

    # Agent 1 performs step
    findings_1 = coord1.run_graph_investigator(inv1, target_symbol="dispatch")
    assert findings_1["node_count"] >= 0

    # Simulate session 1 termination and new session 2 startup
    del coord1

    coord2 = MultiAgentInvestigationCoordinator(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="ws_continuity"
    )
    # Resume investigation
    inv2 = coord2.start_investigation("Trace dispatch dependencies and test coverage", investigation_id="inv_shared_continuity")

    # Agent 2 picks up next task
    findings_2 = coord2.run_test_impact_analyst(inv2, target_symbol="dispatch")
    assert findings_2["selected_test_count"] > 0

    # Record handoff from previous session to new session
    rec = inv2.record_handoff(
        from_agent="agent_graph_investigator_session_1",
        to_agent="agent_test_analyst_session_2",
        task_id="task_session_continuity",
        context={"resumed_from": "inv_shared_continuity"}
    )
    assert rec.from_agent == "agent_graph_investigator_session_1"
    assert rec.to_agent == "agent_test_analyst_session_2"
