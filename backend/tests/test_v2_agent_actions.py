"""
tests/test_v2_agent_actions.py - Verifiable Agent Actions Suite.

Validates the three key agent actions:
1. Graph-Guided Test Selection (select_tests_by_graph)
2. Automated Regression Investigation (investigate_regression_from_diff)
3. Architecture Risk / Blast Radius Investigation (investigate_architecture_risk)
"""

import os
import pytest

from app.agent.actions import AgentActionEngine


@pytest.fixture(scope="module")
def sf_setup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sf_path = os.path.abspath(os.path.join(
        current_dir, "..", "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3"
    ))
    return {"repo_id": "repo_signalforge_aste_d53975", "repo_path": sf_path}


def test_action_1_graph_guided_test_selection(sf_setup):
    """
    Action 1: Graph-guided test selection.
    Verifies that test selection identifies relevant tests based on graph distance
    and checks safety authorization.
    """
    engine = AgentActionEngine(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="ws_actions"
    )

    # 1. Un-authorized execution: must require authorization before running tests
    unauthorized_res = engine.select_tests_by_graph(
        target_symbol="dispatch",
        max_graph_distance=3,
        auto_run=True,
        authorized=False
    )
    assert unauthorized_res["action"] == "select_tests_by_graph"
    assert unauthorized_res["total_candidate_tests"] > 0
    assert len(unauthorized_res["selected_tests"]) > 0
    assert unauthorized_res["test_run_results"]["authorization_required"] is True
    assert unauthorized_res["causally_dependent_on_graph"] is True

    # 2. Authorized execution
    authorized_res = engine.select_tests_by_graph(
        target_symbol="dispatch",
        max_graph_distance=3,
        auto_run=True,
        authorized=True
    )
    assert authorized_res["test_run_results"]["executed"] is True
    assert authorized_res["test_run_results"]["status"] == "ALL_PASSED"

    # Verify tests are prioritized with priority_score and reasons
    top_test = authorized_res["selected_tests"][0]
    assert "priority_score" in top_test
    assert "graph_distance" in top_test
    assert len(top_test["reasons"]) > 0


def test_action_2_automated_regression_investigation(sf_setup):
    """
    Action 2: Automated regression investigation.
    Parses a git diff, maps symbols to graph, and produces evidence-backed diagnosis.
    """
    engine = AgentActionEngine(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="ws_actions"
    )

    synthetic_diff = (
        "--- a/signalforge/worker.py\n"
        "+++ b/signalforge/worker.py\n"
        "@@ -19,4 +19,2 @@ def dispatch(incident):\n"
        "-        release(incident)\n"
    )

    res = engine.investigate_regression_from_diff(
        diff_text=synthetic_diff,
        failing_test_name="tests/test_signalforge.py::test_persistent_failure_releases_budget"
    )

    assert res["action"] == "investigate_regression_from_diff"
    assert any("dispatch" in s or "release" in s for s in res["modified_symbols"])
    assert len(res["impact_analysis"]) > 0
    assert "recorded_finding_id" in res
    assert "root_cause_hypothesis" in res


def test_action_3_architecture_risk_investigation(sf_setup):
    """
    Action 3: Architecture risk investigation.
    Answers "What breaks if this service goes down?" and calculates blast radius.
    """
    engine = AgentActionEngine(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="ws_actions"
    )

    risk_res = engine.investigate_architecture_risk(
        service_or_module_name="dispatch",
        max_depth=3
    )

    assert risk_res["action"] == "investigate_architecture_risk"
    assert risk_res["risk_level"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")
    assert risk_res["blast_radius_count"] >= 0
    assert len(risk_res["recommended_mitigations"]) >= 2
    assert any("circuit-breaker" in m for m in risk_res["recommended_mitigations"])
