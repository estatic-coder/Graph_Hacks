import os
import pytest
from typing import Dict, Any

from app.agent.investigator import GraphInvestigator
from app.agent.pipeline import ReasoningPipeline
from app.agent.tools import TypedGraphTools
from app.agent.resolver import EntityResolver, EntityOrigin
from app.agent.impact import ImpactAnalyzer
from app.agent.control_flow import ControlFlowAnalyzer
from app.memory.manager import GraphMemoryManager
from app.graph.client import falkor_client

ORBIT_REPO_ID = "repo_orbitflow_asteri_1441ae"


@pytest.fixture(scope="module")
def seed_poisoned_memory():
    """
    Seeds poisoned procedural memory and contaminated findings into FalkorDB
    for OrbitFlow:
    1. A Procedure node named 'Workflow for TEST_DISCOVERY'.
    2. A contaminated Finding associating 'Workflow for TEST_DISCOVERY' with 'orbitflow/dispatch.py'.
    """
    graph_name = f"workspace_{ORBIT_REPO_ID}"
    
    # 1. Seed contaminated Procedure
    cypher_proc = """
    MERGE (p:Procedure {id: "proc_poisoned_test_discovery"})
    SET p.proc_id = "test_discovery_poison",
        p.repository_id = $repo_id,
        p.name = "Workflow for TEST_DISCOVERY",
        p.intent_category = "TEST_DISCOVERY",
        p.description = "Playbook for automated test discovery",
        p.query_template = "discover tests for {symbol}"
    RETURN p.id
    """
    falkor_client.safe_query(graph_name, cypher_proc, {"repo_id": ORBIT_REPO_ID})

    # 2. Seed contaminated Finding incorrectly linking procedure to a source file
    cypher_finding = """
    MERGE (f:Finding {id: "finding_poisoned_contaminated_1"})
    SET f.repository_id = $repo_id,
        f.session_id = "sess_poisoned_prior",
        f.title = "Verified behavior of Workflow for TEST_DISCOVERY",
        f.claim = "Verified implementation in orbitflow/dispatch.py",
        f.source_path = "orbitflow/dispatch.py",
        f.start_line = 10,
        f.end_line = 25,
        f.confidence = 0.99,
        f.is_verified = true,
        f.is_stale = false
    RETURN f.id
    """
    falkor_client.safe_query(graph_name, cypher_finding, {"repo_id": ORBIT_REPO_ID})

    yield

    # Teardown / cleanup of poisoned fixtures
    cypher_clean = """
    MATCH (p:Procedure {id: "proc_poisoned_test_discovery"}) DETACH DELETE p
    """
    falkor_client.safe_query(graph_name, cypher_clean)
    cypher_clean_finding = """
    MATCH (f:Finding {id: "finding_poisoned_contaminated_1"}) DETACH DELETE f
    """
    falkor_client.safe_query(graph_name, cypher_clean_finding)


@pytest.fixture
def investigator(seed_poisoned_memory):
    return GraphInvestigator(repo_id=ORBIT_REPO_ID)


@pytest.fixture
def pipeline(seed_poisoned_memory):
    return ReasoningPipeline(repo_id=ORBIT_REPO_ID)


@pytest.fixture
def resolver(seed_poisoned_memory):
    return EntityResolver(repo_id=ORBIT_REPO_ID)


@pytest.fixture
def tools(seed_poisoned_memory):
    return TypedGraphTools(repo_id=ORBIT_REPO_ID)


# ==============================================================================
# 1. Provenance Separation & Symbol Filtering Tests
# ==============================================================================

def test_procedural_memory_never_becomes_repo_symbol(tools, resolver):
    """
    Acceptance Criterion:
    - Procedural memory never appears in repository symbol search.
    - Entity resolver classifies 'Workflow for TEST_DISCOVERY' as PROCEDURAL_MEMORY or CONCEPT, NEVER REPOSITORY.
    """
    # tools.symbol_search must exclude Procedure nodes
    sym_results = tools.symbol_search("Workflow for TEST_DISCOVERY")
    assert len(sym_results) == 0, f"Poisoned Procedure appeared in symbol search: {sym_results}"

    # resolver must mark provenance correctly
    res_entities = resolver.resolve("Workflow for TEST_DISCOVERY")
    # The procedural memory entity itself must never have REPOSITORY origin
    assert not any(
        (ent.origin == EntityOrigin.REPOSITORY and "Workflow for" in ent.name)
        for ent in res_entities
    ), f"Procedural memory was resolved with REPOSITORY origin: {res_entities}"

    proc_ents = [e for e in res_entities if "TEST_DISCOVERY" in e.name or "Workflow for" in e.name]
    for pe in proc_ents:
        assert pe.origin in (EntityOrigin.PROCEDURAL_MEMORY, EntityOrigin.CONCEPT)
        assert pe.origin != EntityOrigin.REPOSITORY

    # Genuine repository symbol has REPOSITORY origin
    genuine = resolver.resolve("dispatch")
    assert len(genuine) > 0
    assert genuine[0].origin == EntityOrigin.REPOSITORY
    assert genuine[0].source_path == "orbitflow/dispatch.py"


# ==============================================================================
# 2. Eight Core Benchmark Queries Under Memory Poisoning
# ==============================================================================

def test_query_1_call_paths_under_memory_poisoning(investigator):
    """
    Query 1: Find call paths from create_order and approve_review to create_label.
    Acceptance: Explicit source symbols remain selected targets; procedural memory is ignored.
    """
    q = "Find call paths from create_order and approve_review to create_label."
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "create_order" in ans
    assert "approve_review" in ans
    assert "create_label" in ans
    assert report.is_verified is True


def test_query_2_carrier_retries_caller_context(investigator):
    """
    Query 2: Analyze carrier retries after create_label raises TimeoutError.
    Acceptance: create_label is target, caller-context finds dispatch(), TimeoutError is CONCEPT,
    3 attempts calculated under MAX_RETRIES = 2.
    """
    q = "If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES=2, and which events follow?"
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "3" in ans or "three" in ans.lower()
    assert "carrier_retry" in ans
    assert "release" in ans
    assert "failed" in ans
    assert report.is_verified is True


def test_query_3_vip_order_analysis(investigator):
    """
    Query 3: Analyze a VIP order.
    Acceptance: Evaluates branch conditions in risk.py / workflow.py without memory distortion.
    """
    q = "A VIP customer submits a low-value order. Is stock reserved, is a shipping label created, and is the customer notified? Cite the exact branches."
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "not reserved" in ans.lower() or "NOT reserved" in ans
    assert "review" in ans
    assert report.is_verified is True


def test_query_4_hypothetical_change_to_dispatch(investigator):
    """
    Query 4: Analyze a hypothetical change to dispatch.
    Acceptance: Change-impact targets dispatch, NOT Workflow for TEST_DISCOVERY.
    Regression test test_carrier_failure_releases_stock is identified.
    """
    q = "If dispatch() stops calling release() on exhausted retries, which workflows and tests are affected?"
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "Target Symbol: Workflow for TEST_DISCOVERY" not in ans
    assert "submit_order" in ans or "dispatch" in ans
    assert "test_carrier_failure_releases_stock" in ans or "test_workflow.py" in ans
    assert report.is_verified is True


def test_query_5_trace_vip_manual_approval_workflow(investigator):
    """
    Query 5: Trace a VIP manual-approval workflow.
    Acceptance: Explains state-mediated second entry point without selecting procedural memory.
    """
    q = "Trace a VIP order from create_order() through approve_review() to create_label(). Explain why the second entry point is required."
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "create_order" in ans
    assert "approve_review" in ans
    assert "create_label" in ans
    assert "second entry point" in ans.lower()
    assert report.is_verified is True


def test_query_6_negative_evidence_kafka(investigator):
    """
    Query 6: Verify Kafka integration is absent.
    Acceptance: Kafka is recognized as CONCEPT, negative-evidence verification works.
    """
    q = "Which function publishes shipment events to Kafka, and where is the Kafka producer configured?"
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "no kafka" in ans.lower() or "No Kafka" in ans
    assert report.is_verified is True


def test_query_7_changing_max_retries_config_impact(investigator):
    """
    Query 7: Analyze changing MAX_RETRIES from 2 to 3.
    Acceptance: Configuration constant MAX_RETRIES resolves to loop owner dispatch(),
    calculating 4 attempts.
    """
    q = "Would changing MAX_RETRIES from 2 to 3 cause three or four carrier attempts? Show the loop condition and increment."
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "4" in ans or "four" in ans.lower()
    assert "while shipment.attempts <= MAX_RETRIES" in ans or "<=" in ans
    assert "orbitflow/dispatch.py" in ans
    assert report.is_verified is True


def test_query_8_untested_branches_in_approve_review(investigator):
    """
    Query 8: Identify untested branches in approve_review.
    Acceptance: Branch analysis targets approve_review, NOT procedural memory.
    """
    q = "Which important failure branch of approve_review() lacks a direct automated test? Show the relevant source branch."
    ans, report = investigator.investigate_with_report(q)

    assert "Workflow for TEST_DISCOVERY" not in ans
    assert "Target Symbol: Workflow for TEST_DISCOVERY" not in ans
    assert "reserve" in ans or "out_of_stock" in ans or "stock" in ans.lower()
    assert "orbitflow/manual_review.py" in ans
    assert report.is_verified is True


# ==============================================================================
# 3. Memory Quarantine & Dry-Run Report Tests
# ==============================================================================

def test_contaminated_memory_quarantine(seed_poisoned_memory):
    """
    Verifies that quarantine_contaminated_memories:
    1. Correctly identifies contaminated findings in dry_run mode without modifying them.
    2. Quarantines contaminated findings in live mode, preventing them from influencing semantic search.
    """
    mem_mgr = GraphMemoryManager(repo_id=ORBIT_REPO_ID, workspace_id="ws_unit")

    # 1. Dry run
    report = mem_mgr.quarantine_contaminated_memories(dry_run=True)
    assert report["dry_run"] is True
    assert report["quarantined_count"] >= 1
    assert any(
        "Workflow for" in item["title"] or "finding_poisoned_contaminated_1" in item["id"]
        for item in report["quarantined_items"]
    )

    # 2. Live run
    live_report = mem_mgr.quarantine_contaminated_memories(dry_run=False)
    assert live_report["dry_run"] is False
    assert live_report["quarantined_count"] >= 1

    # 3. Semantic search must now strictly filter out the quarantined finding
    recalled = mem_mgr.query_semantic_memory(query_text="dispatch")
    assert not any(f.id == "finding_poisoned_contaminated_1" for f in recalled)
    assert not any("Workflow for" in f.title for f in recalled)
