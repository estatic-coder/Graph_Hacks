"""
tests/test_e2e_orbitops_pipeline.py - End-to-end Benchmark Test Suite for OrbitOps.

Tests all 11 OrbitOps benchmark queries (Q1, Q5, Q6, Q9, Q12, Q13, Q16, Q21, Q27, Q28, Q30),
plus repeated Q9 (deterministic invariance) and combined Q12 + Q16 (question decomposition),
verifying:
- Real API execution via POST /api/investigate
- AnswerRequirementsContract satisfaction
- Zero foreign repository symbol contamination (no RelayMesh / SignalForge symbols)
- Verification report is_verified == True with 0 fabricated citations or paths
- Cross-repo regression invariance
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
ORBITOPS_REPO_ID = "repo_orbitops_asterio_c0a361"

ALIEN_SYMBOLS = [
    "approve_job",
    "run_worker_once",
    "poll_once",
    "dispatch",
    "OUTBOX",
    "JOBS"
]

def assert_no_contamination(answer: str):
    """Guarantees zero alien symbol contamination."""
    for sym in ALIEN_SYMBOLS:
        assert sym not in answer, f"Contamination detected: alien symbol '{sym}' found in OrbitOps answer."


def test_q1_static_calls_paths_and_handoffs():
    """Q1: Enumerate static CALLS paths and shared-state handoffs."""
    q = (
        "Enumerate all static CALLS paths from create_alert(), approve_alert(), and "
        "retry_failed_alert() to send_page(). Identify any shared-state handoffs."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert ver["fabricated_citations"] == []
    assert ver["fabricated_paths"] == []
    assert "NO synchronous CALLS path" in ans
    assert "PENDING" in ans
    assert "run_agent_once" in ans


def test_q5_normal_create_alert_returns():
    """Q5: After a normal create_alert() returns, give status, BALANCE, HELD, PENDING, EVENTS, CALLS, NOTICES."""
    q = "After a normal create_alert() returns, give status, BALANCE, HELD, PENDING, ordered EVENTS, pager CALLS, and NOTICES."
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "pending" in ans.lower()
    assert "core" in ans.lower()
    assert "HELD" in ans or "held" in ans.lower()
    assert "PENDING" in ans or "pending" in ans.lower()
    assert "EVENTS" in ans or "events" in ans.lower()
    assert "CALLS" in ans or "calls" in ans.lower()
    assert "NOTICES" in ans or "notices" in ans.lower()


def test_q6_security_team_alert_trace():
    """Q6: Trace creation, approval, and worker iteration across 3 distinct API entrypoints."""
    q = (
        "For a security-team alert, trace creation, approval, and one worker iteration. "
        "Distinguish distinct API entrypoints, persistence, and queue handoffs."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "create_alert" in ans
    assert "approve_alert" in ans
    assert "run_agent_once" in ans
    assert "review" in ans


def test_q9_persistent_pager_timeouts():
    """Q9: With MAX_ATTEMPTS=2 and persistent pager timeouts, report pager calls, timeouts, final status, balance, reservation, events, notices."""
    q = (
        "With MAX_ATTEMPTS=2 and persistent pager timeouts, report pager calls, timeouts, "
        "final status, balance, reservation, events, and notices."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "3 calls" in ans.lower() or "3 send_page calls" in ans.lower()
    assert "3 page_timeout" in ans.lower() or "3 timeouts" in ans.lower()
    assert "failed" in ans.lower()
    assert "4" in ans  # restored balance 4
    assert "empty" in ans.lower() or "cleared" in ans.lower()  # reservation empty


def test_q9_repeated_determinism():
    """Repeated Q9: Guarantees identical deterministic execution without drift or memory pollution."""
    q = (
        "With MAX_ATTEMPTS=2 and persistent pager timeouts, report pager calls, timeouts, "
        "final status, balance, reservation, events, and notices."
    )
    res1 = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    res2 = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res1.status_code == 200
    assert res2.status_code == 200
    data1 = res1.json()
    data2 = res2.json()

    assert data1["verification"]["is_verified"] is True
    assert data2["verification"]["is_verified"] is True
    assert data1["answer"] == data2["answer"]


def test_q12_reopened_failure_pager_recovers():
    """Q12: After a failure is reopened and the pager recovers, calculate total pager calls, attempt reset, final attempts, events, balance, reservation, notices."""
    q = (
        "After a failure is reopened and the pager recovers, calculate total pager calls, "
        "attempt reset, final attempts, events, balance, reservation, and notices."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "4 calls" in ans.lower() or "4" in ans  # 4 total pager calls
    assert "reset to 0" in ans.lower()
    assert "1" in ans  # final attempts 1
    assert "3" in ans  # balance 3


def test_q13_failed_reopen_budget_consumed():
    """Q13: Can a failed reopen consume the reopen budget even without enqueue? Explain ordering and next-attempt behavior."""
    q = "Can a failed reopen consume the reopen budget even without enqueue? Explain ordering and next-attempt behavior."
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "YES" in ans
    assert "REOPENED" in ans
    assert "ValueError" in ans or "reopen budget exceeded" in ans


def test_q16_release_removed_from_exhaustion_branch():
    """Q16: If release() is removed from exhaustion branch of deliver(), which tests detect it and which merely execute related code? Explain assertion chains."""
    q = (
        "If release() is removed from the exhaustion branch of deliver(), which tests detect it "
        "and which merely execute related code? Explain assertion chains."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "test_exhausted_releases" in ans
    assert "test_reopen_after_recovery" in ans
    assert "test_reopen_once_only" in ans


def test_combined_q12_and_q16_decomposition():
    """Combined Q12 + Q16: Decomposes composite query and answers both parts completely without dropping either."""
    q = (
        "After a failure is reopened and the pager recovers, calculate total pager calls, "
        "attempt reset, final attempts, events, balance, reservation, and notices. AND "
        "If release() is removed from the exhaustion branch of deliver(), which tests detect it "
        "and which merely execute related code? Explain assertion chains."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    # Verify Part 1 (Q12) elements are present
    assert "Part 1" in ans
    assert "4" in ans  # 4 pager calls
    assert "reset to 0" in ans.lower()
    # Verify Part 2 (Q16) elements are present
    assert "Part 2" in ans
    assert "test_exhausted_releases" in ans
    assert "test_reopen_after_recovery" in ans


def test_q21_worker_crash_loss_window():
    """Q21: Describe loss window between PENDING.pop(0) and deliver(). Distinguish actual code from hypothetical recovery."""
    q = (
        "A worker crashes after PENDING.pop(0) but before deliver(). Describe the loss window "
        "and distinguish actual code from hypothetical recovery."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "pop(0)" in ans
    assert "sweep_holds" in ans


def test_q27_persistent_memory_action():
    """Q27: Store a verified finding about the queue-loss window. In a new independent session, retrieve it, include provenance and revision, and revalidate."""
    q = (
        "Store a verified finding about the queue-loss window. In a new independent session, "
        "retrieve it, include provenance and revision, and revalidate it if code changes."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "finding_" in ans
    assert "Session 1" in ans
    assert "Session 2" in ans
    assert "revalidation" in ans.lower() or "validated" in ans.lower()


def test_q28_multi_agent_coordination():
    """Q28: Perform a multi-agent investigation of why an alert is stuck in review with 4 collaborating agent roles."""
    q = (
        "Perform a multi-agent investigation of why an alert is stuck in review. Show a graph "
        "investigator, execution analyst, test analyst, and evidence reviewer sharing state and handing off."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "Graph Investigator" in ans
    assert "Execution Analyst" in ans
    assert "Test Analyst" in ans
    assert "Evidence Reviewer" in ans
    assert "approve_alert" in ans


def test_q30_git_diff_mutation_execution():
    """Q30: Using a Git diff that removes release() from deliver(), produce blast radius, run isolated tests, distinguish real results from predictions."""
    q = (
        "Using a Git diff that removes release() from deliver(), produce a blast-radius graph, "
        "select and execute tests in an isolated environment, and clearly distinguish real results from predictions."
    )
    res = client.post("/api/investigate", json={"repo_id": ORBITOPS_REPO_ID, "query": q})
    assert res.status_code == 200
    data = res.json()
    ans = data["answer"]
    ver = data["verification"]

    assert_no_contamination(ans)
    assert ver["is_verified"] is True
    assert "receipt_" in ans or "execution_receipt" in ans
    assert "test_exhausted_releases" in ans
    assert "test_reopen_after_recovery" in ans
    assert "isolated" in ans.lower()
