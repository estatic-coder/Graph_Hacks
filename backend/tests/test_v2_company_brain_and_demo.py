"""
tests/test_v2_company_brain_and_demo.py - Company Brain, Hackathon Demo & Incremental Engine Suite.

Validates:
1. Company Brain (Module ownership, ADR retrieval, issue tracking).
2. All 6 scenes of Hackathon Demo (The AI Engineering Incident Investigator).
3. Incremental Indexer (Hash caching, skipping unchanged files).
4. 3-Tier Execution Router (Deterministic vs Hybrid vs Deep reasoning).
"""

import os
import pytest

from app.knowledge.company_brain import CompanyBrain
from app.agent.demo_scenario import IncidentInvestigatorDemo
from app.ingestion.incremental import IncrementalIndexer, ThreeTierExecutionRouter


@pytest.fixture(scope="module")
def sf_setup():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sf_path = os.path.abspath(os.path.join(
        current_dir, "..", "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3"
    ))
    return {"repo_id": "repo_signalforge_aste_d53975", "repo_path": sf_path}


def test_company_brain_ownership_and_adrs():
    brain = CompanyBrain(repo_id="repo_signalforge_aste_d53975")

    # Ownership query
    own_res = brain.answer_company_question("Who owns worker.py?")
    assert own_res["category"] == "OWNERSHIP"
    assert "Sarah Chen" in own_res["answer"]
    assert "Core Platform Engineering" in own_res["answer"]
    assert len(own_res["citations"]) > 0

    # ADR query
    adr_res = brain.answer_company_question("Which architectural decision explains its retry policy?")
    assert adr_res["category"] == "ARCHITECTURAL_DECISION"
    assert "ADR-004" in adr_res["answer"]
    assert "docs/architecture/decisions/ADR-004-retry-policy.md" in adr_res["citations"]


def test_incremental_indexer_and_hash_caching(sf_setup):
    indexer = IncrementalIndexer(repo_id=sf_setup["repo_id"], repo_path=sf_setup["repo_path"])

    # First scan: cold index
    idx1 = indexer.index_incrementally()
    assert idx1["files_processed"] > 0
    assert idx1["parsed_symbols"] > 0

    # Second scan: incremental index skips all unchanged files
    idx2 = indexer.index_incrementally()
    assert idx2["is_incremental"] is True
    assert idx2["files_skipped_unchanged"] > 0
    assert idx2["files_processed"] == 0  # 0 files re-parsed!


def test_three_tier_execution_router():
    router = ThreeTierExecutionRouter()

    # Tier 1 query
    t1 = router.route_query_tier("Enumerate static calls from create_incident to send")
    assert t1["tier"] == 1
    assert t1["tier_name"] == "DETERMINISTIC"
    assert t1["estimated_llm_cost"] == "ZERO_TOKENS"

    # Tier 2 query
    t2 = router.route_query_tier("Describe the overall intake architecture")
    assert t2["tier"] == 2
    assert t2["tier_name"] == "HYBRID"

    # Tier 3 query
    t3 = router.route_query_tier("Simulate multi-phase replay when worker exhausts retries again")
    assert t3["tier"] == 3
    assert t3["tier_name"] == "DEEP_REASONING"


def test_hackathon_demo_all_6_scenes(sf_setup):
    """Verifies that all 6 scenes of the Hackathon Demo run end-to-end cleanly."""
    demo = IncidentInvestigatorDemo(
        repo_id=sf_setup["repo_id"],
        repo_path=sf_setup["repo_path"]
    )

    # Scene 1: Graph reasoning
    s1 = demo.run_scene_1_graph_reasoning()
    assert s1["scene"] == 1
    assert "dispatch" in s1["target"]

    # Scene 2: Graph-driven action
    s2 = demo.run_scene_2_graph_driven_action()
    assert s2["scene"] == 2
    assert s2["causally_dependent_on_graph"] is True
    assert len(s2["selected_tests"]) > 0

    # Scene 3: Persistent memory
    s3 = demo.run_scene_3_persistent_memory()
    assert s3["scene"] == 3
    assert s3["cross_session_continuity"] is True
    assert s3["recalled_findings_count"] > 0

    # Scene 4: Multi-agent coordination
    s4 = demo.run_scene_4_multi_agent_coordination()
    assert s4["scene"] == 4
    assert s4["tasks_completed"] == 4
    assert s4["handoff_count"] == 3

    # Scene 5: Decision explainability
    s5 = demo.run_scene_5_decision_explainability()
    assert s5["scene"] == 5
    assert len(s5["provenance_chain"]) == 13

    # Scene 6: Company brain
    s6 = demo.run_scene_6_company_brain()
    assert s6["scene"] == 6
    assert "Sarah Chen" in s6["ownership_answer"]
    assert "ADR-004" in s6["adr_answer"]
