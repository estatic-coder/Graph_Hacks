import pytest
import os
from app.agent.investigator import GraphInvestigator
from app.agent.pipeline import ReasoningPipeline, ErrorState
from app.agent.tools import TypedGraphTools
from app.agent.resolver import EntityResolver
from app.agent.impact import ImpactAnalyzer
from app.agent.control_flow import ControlFlowAnalyzer

ORBIT_REPO_ID = "repo_orbitflow_asteri_1441ae"
SENTINEL_REPO_ID = "repo_sentinelshop_ast_e1e991"
AEGIS_REPO_ID = "repo_aegisops_asterio_158e16"

@pytest.fixture
def investigator():
    return GraphInvestigator(repo_id=ORBIT_REPO_ID)

@pytest.fixture
def pipeline():
    return ReasoningPipeline(repo_id=ORBIT_REPO_ID)

@pytest.fixture
def tools():
    return TypedGraphTools(repo_id=ORBIT_REPO_ID)

@pytest.fixture
def resolver():
    return EntityResolver(repo_id=ORBIT_REPO_ID)

@pytest.fixture
def control_flow():
    from app.repositories.manager import RepositoryManager
    meta = RepositoryManager().get_repository(ORBIT_REPO_ID)
    return ControlFlowAnalyzer(repo_path=meta.source_path if meta else None)


def test_priority0_three_repositories_isolation():
    """
    Priority 0: Verify strict repository isolation across SentinelShop, AegisOps, and OrbitFlow.
    Ensures:
    1. Zero cross-repository symbol resolution or discovery.
    2. Zero leakage of parent directory or workspace files (e.g. MLchallenge, asteria).
    3. Missing or invalid repository ID raises structured errors.
    4. Impact analysis risk scoring and evidence are strictly scoped to the repository graph.
    """
    orbit_tools = TypedGraphTools(repo_id=ORBIT_REPO_ID)
    sentinel_tools = TypedGraphTools(repo_id=SENTINEL_REPO_ID)
    aegis_tools = TypedGraphTools(repo_id=AEGIS_REPO_ID)

    # 1. OrbitFlow symbols must NOT appear in SentinelShop or AegisOps
    orbit_symbols = ["dispatch", "create_label", "approve_review", "submit_order"]
    for sym in orbit_symbols:
        s_res = sentinel_tools.symbol_search(sym)
        assert len(s_res) == 0, f"Symbol '{sym}' from OrbitFlow leaked into SentinelShop!"
        a_res = aegis_tools.symbol_search(sym)
        assert len(a_res) == 0, f"Symbol '{sym}' from OrbitFlow leaked into AegisOps!"

    # 2. SentinelShop symbols must NOT appear in OrbitFlow or AegisOps
    s_sym = "authorize_payment"
    assert len(orbit_tools.symbol_search(s_sym)) == 0, "authorize_payment leaked into OrbitFlow!"
    assert len(aegis_tools.symbol_search(s_sym)) == 0, "authorize_payment leaked into AegisOps!"

    # 3. AegisOps symbols must NOT appear in OrbitFlow or SentinelShop
    a_sym = "isolate_host"
    assert len(orbit_tools.symbol_search(a_sym)) == 0, "isolate_host leaked into OrbitFlow!"
    assert len(sentinel_tools.symbol_search(a_sym)) == 0, "isolate_host leaked into SentinelShop!"

    # 4. Strict git diff scoping: OrbitFlow diff must never climb into parent repo (no MLchallenge or asteria)
    impact_analyzer = ImpactAnalyzer(repo_id=ORBIT_REPO_ID)
    diff = impact_analyzer.read_local_diff()
    assert "MLchallenge" not in diff
    assert "asteria" not in diff

    # 5. Missing or invalid repository ID must raise structured ValueError
    with pytest.raises(ValueError):
        GraphInvestigator(repo_id="")
    with pytest.raises(ValueError):
        ReasoningPipeline(repo_id="nonexistent_repo_id_12345")
    with pytest.raises(ValueError):
        ImpactAnalyzer(repo_id="invalid_repo_xyz")

    # 6. Impact analysis on dispatch in OrbitFlow must not leak any external symbols
    disp_impact = impact_analyzer.analyze_symbol_impact("dispatch")
    for ent in disp_impact.impacted_entities:
        assert ent.source_path and not ent.source_path.startswith("/")
        assert "MLchallenge" not in ent.name and "asteria" not in ent.name
        assert not ent.source_path.startswith("..")


def test_q1_multi_entry_paths_and_shared_functions(investigator):
    """
    Stage 1: Multi-entry call paths from create_order() and approve_review() to create_label().
    Identifies shared functions and cites each hop.
    """
    q = "Find every function call path from create_order() and approve_review() to create_label(). Which functions are shared? Cite each hop."
    ans, report = investigator.investigate_with_report(q)

    # Discovered paths
    assert "create_order -> submit_order -> dispatch -> create_label" in ans
    assert "approve_review -> dispatch -> create_label" in ans

    # Shared functions
    assert "Shared Functions" in ans
    assert "dispatch" in ans and "create_label" in ans

    # Citations for each hop
    assert "orbitflow/api.py" in ans
    assert "orbitflow/workflow.py" in ans
    assert "orbitflow/manual_review.py" in ans
    assert "orbitflow/dispatch.py" in ans

    assert report.is_verified is True
    assert report.paths_valid >= 2
    assert len(report.fabricated_paths) == 0


def test_q2_retry_semantics_and_exhaustion(investigator):
    """
    Stage 2: Retry semantics when create_label() raises TimeoutError with MAX_RETRIES=2.
    Determines 3 attempts, 3 carrier_retry events, stock release, failed event, and notification.
    """
    q = "If create_label() always raises TimeoutError, how many attempts occur when MAX_RETRIES=2, and which events, stock changes, and customer notifications follow?"
    ans, report = investigator.investigate_with_report(q)

    # Attempt calculation
    assert "3" in ans or "three" in ans.lower()
    assert "carrier_retry" in ans

    # Stock rollback and events on exhaustion
    assert "release" in ans
    assert "failed" in ans
    assert "notify_customer" in ans

    assert report.is_verified is True
    assert len(report.fabricated_citations) == 0


def test_q3_vip_low_value_order_branch(investigator):
    """
    Stage 4: VIP customer submitting low-value order.
    Determines that stock is NOT reserved, label is NOT created, customer is NOT notified.
    """
    q = "A VIP customer submits a low-value order. Is stock reserved, is a shipping label created, and is the customer notified? Cite the exact branches."
    ans, report = investigator.investigate_with_report(q)

    # Negative side effects
    assert "NOT reserved" in ans or "not reserved" in ans.lower() or "stock_reserved: False" in ans
    assert "NOT created" in ans or "not created" in ans.lower() or "label_created: False" in ans
    assert "NOT notified" in ans or "not notified" in ans.lower() or "customer_notified: False" in ans

    # Saved state
    assert "review" in ans
    assert "orbitflow/risk.py" in ans
    assert "orbitflow/workflow.py" in ans

    assert report.is_verified is True


def test_q4_dispatch_stopping_release_impact(investigator):
    """
    Stage 4: If dispatch() stops calling release() on exhausted retries, verify affected workflows and tests.
    """
    q = "If dispatch() stops calling release() on exhausted retries, which workflows and tests are affected? Distinguish automatic orders from manually approved orders."
    ans, report = investigator.investigate_with_report(q)

    # Both workflows
    assert "submit_order" in ans or "Automatic" in ans
    assert "approve_review" in ans or "manual" in ans.lower()
    assert "stock" in ans.lower() or "inventory" in ans.lower()

    # Tests affected
    assert "test_workflow.py" in ans
    assert "test_carrier_failure_releases_stock" in ans

    assert report.is_verified is True


def test_q5_manual_approval_workflow_and_second_entry_point(investigator):
    """
    Stage 3: Trace VIP order from create_order() through approve_review() to create_label().
    Explains why the second entry point is required (state-mediated persistence).
    """
    q = "Trace a VIP order from create_order() through approve_review() to create_label(). Explain why the second entry point is required."
    ans, report = investigator.investigate_with_report(q)

    assert "create_order" in ans
    assert "submit_order" in ans
    assert "approve_review" in ans
    assert "create_label" in ans
    assert "second entry point" in ans.lower()
    assert "SHIPMENTS" in ans or "state" in ans.lower()

    assert report.is_verified is True


def test_q6_negative_evidence_kafka(investigator):
    """
    Stage 6: Negative evidence verification for Kafka integration.
    """
    q = "Which function publishes shipment events to Kafka, and where is the Kafka producer configured?"
    ans, report = investigator.investigate_with_report(q)

    # Negative conclusion and scope of search
    assert "No Kafka" in ans or "no kafka" in ans.lower()
    assert "Scope of Search" in ans or "scope" in ans.lower()

    # Grounded reality
    assert "EVENTS" in ans
    assert "orbitflow/storage.py" in ans

    assert report.is_verified is True


def test_q7_off_by_one_loop_attempts(investigator):
    """
    Stage 2: Loop condition and attempt count when MAX_RETRIES changes from 2 to 3.
    """
    q = "Would changing MAX_RETRIES from 2 to 3 cause three or four carrier attempts? Show the loop condition and increment."
    ans, report = investigator.investigate_with_report(q)

    # Four attempts
    assert "four" in ans.lower() or "4" in ans

    # Loop condition and increment
    assert "while shipment.attempts <= MAX_RETRIES" in ans or "<=" in ans
    assert "shipment.attempts += 1" in ans or "+= 1" in ans
    assert "orbitflow/dispatch.py" in ans

    assert report.is_verified is True
    assert len(report.fabricated_paths) == 0


def test_q8_order_visibility_out_of_stock(investigator):
    """
    Stage 4: Does get_order() return a shipment for an out-of-stock order?
    """
    q = "Does get_order() return a shipment for an out-of-stock order? Why?"
    ans, report = investigator.investigate_with_report(q)

    # Returns None / does not return
    assert "None" in ans or "does NOT return" in ans or "no" in ans.lower()
    assert "save_shipment" in ans
    assert "SHIPMENTS" in ans

    assert report.is_verified is True


def test_q9_audit_events_distinction(investigator):
    """
    Stage 4: Compare audit events for VIP review, successful shipping, and carrier failure.
    """
    q = "Compare audit events for VIP review, successful shipping, and persistent carrier failure."
    ans, report = investigator.investigate_with_report(q)

    assert "review" in ans
    assert "shipped" in ans
    assert "carrier_retry" in ans
    assert "failed" in ans

    assert report.is_verified is True


def test_q10_approve_review_untested_failure_branch(investigator):
    """
    Stage 5: Identify untested failure branch of approve_review().
    """
    q = "Which important failure branch of approve_review() lacks a direct automated test? Show the relevant source branch."
    ans, report = investigator.investigate_with_report(q)

    # Untested branch
    assert "reserve" in ans or "out_of_stock" in ans or "stock" in ans.lower()
    assert "orbitflow/manual_review.py" in ans

    assert report.is_verified is True
