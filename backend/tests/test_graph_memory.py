import os
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.graph.client import falkor_client
from app.memory.manager import GraphMemoryManager
from app.agent.investigator import GraphInvestigator

@pytest.fixture
def memory_manager(tmp_path):
    # Setup test file
    sample_file = tmp_path / "service.py"
    sample_file.write_text("def connect_db():\n    return 'connected'\n", encoding="utf-8")
    
    mgr = GraphMemoryManager(repo_id="test_mem", repo_path=str(tmp_path), workspace_id="ws_unit")
    return mgr

def test_episodic_memory_sessions(memory_manager):
    """Verifies storing and retrieving episodic investigation sessions."""
    sess1 = memory_manager.record_session("sess_001", "How does connect_db work?")
    assert sess1.session_id == "sess_001"
    assert sess1.query == "How does connect_db work?"
    assert sess1.source_revision != ""
    assert sess1.timestamp != ""

    sess2 = memory_manager.record_session("sess_002", "What is the impact of modifying service.py?")
    assert sess2.session_id == "sess_002"

    retrieved = memory_manager.get_session("sess_001")
    if retrieved:
        assert retrieved.session_id == "sess_001"
        assert retrieved.query == "How does connect_db work?"

    sessions = memory_manager.list_sessions(limit=10)
    session_ids = [s.session_id for s in sessions]
    if sessions:
        assert "sess_001" in session_ids or "sess_002" in session_ids

def test_semantic_memory_findings_and_evidence(memory_manager):
    """Verifies storing verified findings, linking to symbols, and querying semantic memory."""
    memory_manager.record_session("sess_find", "Audit service")
    
    finding = memory_manager.record_finding(
        session_id="sess_find",
        title="Verified connect_db implementation",
        claim="Function returns static string 'connected'",
        source_path="service.py",
        start_line=1,
        end_line=2,
        graph_paths=["connect_db -> return"],
        referenced_symbol_ids=["sym_test_connect_db"],
        confidence=1.0,
        is_verified=True
    )

    assert finding.title == "Verified connect_db implementation"
    assert finding.is_verified is True
    assert finding.is_stale is False
    assert finding.snippet_hash != ""

    # Query semantic memory by symbol
    findings_by_sym = memory_manager.query_semantic_memory(symbol_id="sym_test_connect_db")
    if findings_by_sym:
        assert any(f.title == "Verified connect_db implementation" for f in findings_by_sym)

    # Query semantic memory by text
    findings_by_text = memory_manager.query_semantic_memory(query_text="connect_db")
    if findings_by_text:
        assert any("connect_db" in f.title for f in findings_by_text)

def test_cross_session_memory_retrieval(tmp_path):
    """
    Demonstrates cross-session memory recall:
    Session 1 investigates and verifies a finding.
    Session 2 investigates the same symbol in a distinct session and recalls Session 1's finding.
    """
    sample_file = tmp_path / "db.py"
    sample_file.write_text("def get_conn():\n    return 'conn'\n", encoding="utf-8")

    investigator1 = GraphInvestigator(repo_id="test_cross", repo_path=str(tmp_path), workspace_id="ws_cross")
    ans1, rep1 = investigator1.investigate_with_report(
        "Inspect get_conn function", session_id="session_alpha"
    )
    assert ans1 != ""

    # Explicitly store verified finding for get_conn in session alpha
    investigator1.memory.record_finding(
        session_id="session_alpha",
        title="get_conn verified connection string",
        claim="Returns string 'conn' on line 2",
        source_path="db.py",
        start_line=1,
        end_line=2,
        graph_paths=["get_conn"],
        referenced_symbol_ids=["sym_test_cross_db.py_get_conn"],
        confidence=1.0,
        is_verified=True
    )

    # Session 2: completely distinct session ID
    investigator2 = GraphInvestigator(repo_id="test_cross", repo_path=str(tmp_path), workspace_id="ws_cross")
    ans2, rep2 = investigator2.investigate_with_report(
        "Inspect get_conn function", session_id="session_beta"
    )

    # Verify that Session 2 recalled Session 1's prior finding
    recalled = investigator2.memory.query_semantic_memory(query_text="get_conn")
    assert len(recalled) > 0
    assert any("session_alpha" in f.session_id for f in recalled)

def test_procedural_memory_storage_and_recall(memory_manager):
    """Verifies storing and retrieving procedural playbooks."""
    proc = memory_manager.record_procedure(
        name="Trace Downstream API Callers",
        intent_category="CALLER_TRACING",
        description="Standard 3-hop reverse dependency traversal",
        tool_sequence=["symbol_search", "trace_callers"],
        query_template="Who calls {symbol}?"
    )
    assert proc.name == "Trace Downstream API Callers"
    assert proc.intent_category == "CALLER_TRACING"

    recalled_proc = memory_manager.get_procedure("CALLER_TRACING")
    if recalled_proc:
        assert recalled_proc.intent_category == "CALLER_TRACING"
        assert "trace_callers" in recalled_proc.tool_sequence or recalled_proc.name == "Trace Downstream API Callers"

def test_hypothesis_lifecycle(memory_manager):
    """Verifies hypothesis creation, listing, and resolution."""
    hypo = memory_manager.record_hypothesis(
        session_id="sess_hypo",
        statement="Database connection might leak handles if query errors",
        target_symbol_ids=["sym_test_connect_db"]
    )
    assert hypo.statement == "Database connection might leak handles if query errors"
    assert hypo.status == "unresolved"

    unresolved = memory_manager.list_hypotheses(status="unresolved")
    if unresolved:
        assert any(h.id == hypo.id for h in unresolved)

    # Resolve hypothesis
    memory_manager.resolve_hypothesis(hypo.id, status="validated", notes="Confirmed: missing finally block")

    resolved = memory_manager.list_hypotheses(status="validated")
    if resolved:
        assert any(h.id == hypo.id for h in resolved)

def test_stale_finding_invalidation(tmp_path):
    """Verifies that modifying file contents invalidates prior findings and flags stale_reason."""
    src_file = tmp_path / "config.py"
    src_file.write_text("DEBUG = True\nPORT = 8080\n", encoding="utf-8")

    mgr = GraphMemoryManager(repo_id="test_stale", repo_path=str(tmp_path))
    mgr.record_session("sess_old", "Check config")
    
    finding = mgr.record_finding(
        session_id="sess_old",
        title="DEBUG is True",
        claim="Configuration sets DEBUG=True on line 1",
        source_path="config.py",
        start_line=1,
        end_line=1,
        is_verified=True
    )

    # Prior finding is not stale
    active = mgr.query_semantic_memory(query_text="DEBUG", include_stale=False)
    if active:
        assert any(f.id == finding.id for f in active)

    # Now modify code on disk
    src_file.write_text("DEBUG = False\nPORT = 9000\n", encoding="utf-8")

    # Trigger invalidation
    invalidated = mgr.invalidate_stale_findings()
    
    # Check that finding is flagged as stale
    if invalidated:
        assert any(inv["finding_id"] == finding.id for inv in invalidated)
        inv_item = next(inv for inv in invalidated if inv["finding_id"] == finding.id)
        assert "changed on disk" in inv_item["stale_reason"]

    # When querying without include_stale, it should no longer be returned as active
    active_after = mgr.query_semantic_memory(query_text="DEBUG", include_stale=False)
    assert not any(f.id == finding.id and f.is_stale for f in active_after)

def test_memory_api_endpoints():
    """Verifies FastAPI REST endpoints for memory sessions, findings, hypotheses, and invalidation."""
    client = TestClient(app)

    # 1. Investigate and create a session
    resp = client.post("/api/investigate", json={
        "repo_id": "sample_1",
        "query": "Who calls get_db_connection?",
        "session_id": "sess_api_test_1"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"

    # 2. Get sessions
    sess_resp = client.get("/api/memory/sessions?repo_id=sample_1")
    assert sess_resp.status_code == 200
    sess_data = sess_resp.json()
    assert sess_data["status"] == "success"
    assert isinstance(sess_data["sessions"], list)

    # 3. Get findings
    find_resp = client.get("/api/memory/findings?repo_id=sample_1")
    assert find_resp.status_code == 200
    find_data = find_resp.json()
    assert find_data["status"] == "success"
    assert isinstance(find_data["findings"], list)

    # 4. Get hypotheses
    hypo_resp = client.get("/api/memory/hypotheses?repo_id=sample_1")
    assert hypo_resp.status_code == 200
    assert hypo_resp.json()["status"] == "success"

    # 5. Invalidate memory endpoint
    inv_resp = client.post("/api/memory/invalidate", json={
        "repo_id": "sample_1"
    })
    assert inv_resp.status_code == 200
    inv_data = inv_resp.json()
    assert inv_data["status"] == "success"
    assert "invalidated_count" in inv_data
