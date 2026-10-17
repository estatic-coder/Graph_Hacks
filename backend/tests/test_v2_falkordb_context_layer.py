"""
tests/test_v2_falkordb_context_layer.py - FalkorDB Context Layer & Causal Dependency Suite.

Validates:
1. Schema coverage (Code Intelligence, Agent Memory, Company Knowledge, RelTypes).
2. The 13-step Graph-Driven Agent Loop with decision provenance.
3. Causal Graph Dependency:
   - When graph relationships change, agent decisions and tool selections change.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

from app.graph.schema import NodeType, RelType
from app.agent.decision_engine import GraphDecisionEngine


@pytest.fixture(scope="module")
def sf_setup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sf_path = os.path.abspath(os.path.join(
        current_dir, "..", "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3"
    ))
    return {"repo_id": "repo_signalforge_aste_d53975", "repo_path": sf_path}


def test_schema_coverage_and_types():
    """Validates that all P1 requested node types and edge types exist in schema."""
    # Code intelligence
    assert NodeType.REVISION == "Revision"
    assert NodeType.CALLSITE == "CallSite"
    assert NodeType.BRANCH == "Branch"
    assert NodeType.STATE_STORE == "StateStore"
    assert NodeType.EXTERNAL_SERVICE == "ExternalService"
    assert NodeType.CONFIGURATION == "Configuration"

    # Agent memory
    assert NodeType.AGENT == "Agent"
    assert NodeType.SESSION == "Session"
    assert NodeType.OBSERVATION == "Observation"
    assert NodeType.ACTION == "Action"
    assert NodeType.OUTCOME == "Outcome"
    assert NodeType.EPISODE == "Episode"
    assert NodeType.FACT == "Fact"
    assert NodeType.EVIDENCE == "Evidence"

    # Company knowledge
    assert NodeType.PERSON == "Person"
    assert NodeType.TEAM == "Team"
    assert NodeType.PROJECT == "Project"
    assert NodeType.ISSUE == "Issue"
    assert NodeType.PULL_REQUEST == "PullRequest"
    assert NodeType.COMMIT == "Commit"
    assert NodeType.DOCUMENT == "Document"
    assert NodeType.DECISION_RECORD == "DecisionRecord"
    assert NodeType.SYSTEM == "System"

    # Edge types
    for rel in ["CALLS", "DEPENDS_ON", "READS_STATE", "WRITES_STATE", "ENQUEUES", "DEQUEUES",
                "TESTS", "COVERS", "OBSERVED", "SUPPORTS", "CONTRADICTS", "DECIDED",
                "EXECUTED", "PRODUCED", "LEARNED", "REMEMBERS", "HANDOFF_TO", "OWNED_BY",
                "WORKED_ON", "DOCUMENTED_IN", "AFFECTS"]:
        assert hasattr(RelType, rel)


def test_13_step_graph_driven_agent_loop(sf_setup):
    """Validates execution of the 13-step Graph-Driven Agent Loop."""
    engine = GraphDecisionEngine(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="test_ws"
    )

    result = engine.execute_agent_loop(
        objective="Assess resilience of notification dispatch under transport failure",
        target_symbol="dispatch",
        authorize_actions=True
    )

    assert result["target"] == "dispatch"
    assert len(result["decision_steps"]) == 13
    assert result["chosen_algorithm"] in ("reverse_dependencies", "shortest_path", "impact_subgraph")
    assert result["selected_action"] in ("SELECT_AND_RUN_TESTS", "BLAST_RADIUS_AUDIT", "NO_ACTION_REQUIRED")
    assert "Graph Evidence" in result["explanation"]
    assert "graph_influencing_path" in result


def test_causal_graph_dependency(sf_setup):
    """
    CRITICAL TEST: The agent must make different decisions when graph relationships change.
    """
    engine = GraphDecisionEngine(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"],
        workspace_id="test_ws_causal"
    )

    # Condition A: Graph has high fan-in callers (>= 2 callers) -> Agent decides to run regression tests
    context_high_fanin = {
        "symbol": "dispatch",
        "inbound_callers": ["poll_once", "run_worker_once", "manual_audit"],
        "outbound_calls": ["send"],
        "has_circuit_breaker": False,
        "is_critical_path": True,
        "influencing_path": "poll_once -> dispatch -> send"
    }

    with patch.object(engine, "_retrieve_graph_context", return_value=context_high_fanin):
        res_a = engine.execute_agent_loop("Investigate dispatch", target_symbol="dispatch")
        assert res_a["chosen_algorithm"] == "reverse_dependencies"
        assert res_a["selected_action"] == "SELECT_AND_RUN_TESTS"
        assert "critical path" in res_a["causal_graph_factor"].lower()

    # Condition B: Protective circuit breaker edge added to the graph -> Agent decides NO action required!
    context_with_breaker = {
        "symbol": "dispatch",
        "inbound_callers": ["poll_once"],
        "outbound_calls": ["circuit_breaker", "send"],
        "has_circuit_breaker": True,
        "is_critical_path": False,
        "influencing_path": "poll_once -> dispatch -> circuit_breaker"
    }

    with patch.object(engine, "_retrieve_graph_context", return_value=context_with_breaker):
        res_b = engine.execute_agent_loop("Investigate dispatch", target_symbol="dispatch")
        assert res_b["selected_action"] == "NO_ACTION_REQUIRED"
        assert "circuit breaker" in res_b["causal_graph_factor"].lower()

    # Verify decisions are causally different!
    assert res_a["selected_action"] != res_b["selected_action"]
    assert res_a["chosen_algorithm"] != res_b["chosen_algorithm"]
