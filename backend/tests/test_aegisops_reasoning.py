import pytest
from app.agent.investigator import GraphInvestigator
from app.agent.pipeline import ReasoningPipeline, ErrorState
from app.agent.tools import TypedGraphTools
from app.agent.resolver import EntityResolver
from app.agent.control_flow import ControlFlowAnalyzer

AEGIS_REPO_ID = "repo_aegisops_asterio_158e16"

@pytest.fixture
def investigator():
    return GraphInvestigator(repo_id=AEGIS_REPO_ID)

@pytest.fixture
def pipeline():
    return ReasoningPipeline(repo_id=AEGIS_REPO_ID)

@pytest.fixture
def tools():
    return TypedGraphTools(repo_id=AEGIS_REPO_ID)

@pytest.fixture
def resolver():
    return EntityResolver(repo_id=AEGIS_REPO_ID)

@pytest.fixture
def control_flow():
    from app.repositories.manager import RepositoryManager
    meta = RepositoryManager().get_repository(AEGIS_REPO_ID)
    return ControlFlowAnalyzer(repo_path=meta.source_path if meta else None)


def test_q1_multihop_call_path_with_conditions(investigator, pipeline):
    """Q1: Trace path from ingest_alert() to isolate_host() with branch conditions and citations."""
    q = "Trace the function call path from ingest_alert() to isolate_host(). Which conditions must be true for isolation to occur? Show source file and line evidence."
    ans, report = investigator.investigate_with_report(q)
    
    # Path verification
    assert "ingest_alert -> process_event -> open_incident -> execute_response -> isolate_host" in ans
    assert "process_event" in ans and "open_incident" in ans and "execute_response" in ans
    
    # Condition verification
    assert "critical" in ans.lower()
    assert "TRUSTED_HOSTS" in ans
    assert "AUTO_ISOLATE" in ans
    
    # Verification report: valid citations and graph path
    assert report.is_verified is True
    assert report.citations_valid >= 5
    assert report.paths_valid >= 1
    assert len(report.fabricated_citations) == 0
    assert len(report.fabricated_paths) == 0


def test_q1_path_not_found_on_reverse(pipeline, tools):
    """Stage 1: Verify PATH_NOT_FOUND on reverse or disconnected symbols."""
    # Directed CALLS path does not go from isolate_host to ingest_alert
    res = tools.find_call_paths("isolate_host", "ingest_alert")
    assert res.get("found") is False
    assert res.get("error_code") == "PATH_NOT_FOUND"


def test_q2_classify_event_misclassification_impact(investigator):
    """Q2: If classify_event() incorrectly labels all malware as ignore, verify executed vs skipped operations."""
    q = "If classify_event() incorrectly labels all malware as ignore, which functions, incident records, notifications, remediation actions, audit logs, and tests could be affected? Separate operations that are skipped from operations still executed."
    ans, report = investigator.investigate_with_report(q)
    
    # Executed operations
    assert "normalize_event" in ans
    assert "record_audit('ignored'" in ans or "ignored" in ans
    
    # Skipped operations
    assert "open_incident" in ans
    assert "save_incident" in ans
    assert "isolate_host" in ans
    assert "notify_operations" in ans
    
    # Affected tests cited
    assert "test_rules.py" in ans
    assert "test_pipeline.py" in ans


def test_q3_trusted_host_control_flow(investigator):
    """Q3: Event arrives from core-db. Verify AegisOps does NOT isolate it and traces notifications."""
    q = "A critical-severity malware event arrives from core-db. Will AegisOps isolate it? Trace the exact reason and list which notifications occur."
    ans, report = investigator.investigate_with_report(q)
    
    assert "NOT isolate" in ans or "will_isolate: False" in ans or "not isolate" in ans.lower()
    assert "TRUSTED_HOSTS" in ans
    assert "review" in ans
    assert "notify_security_team" in ans
    assert "notify_operations" in ans


def test_q4_benign_cpu_spike_branch_order(investigator):
    """Q4: For benign cpu_spike with severity 9, verify which operations run vs skipped."""
    q = "For a benign cpu_spike event with severity 9, which operations run, and which operations are skipped?"
    ans, report = investigator.investigate_with_report(q)
    
    # Run
    assert "normalize_event" in ans
    assert "classify_event" in ans
    assert "record_audit('ignored'" in ans or "ignored" in ans
    
    # Skipped
    assert "open_incident" in ans
    assert "isolate_host" in ans


def test_q5_direct_vs_indirect_test_discovery(investigator):
    """Q5: Discover direct tests (test_rules.py) vs indirect tests (test_pipeline.py, test_api.py)."""
    q = "Which tests directly verify classify_event() and which test its effects indirectly through process_event() or ingest_alert()? Show graph paths."
    ans, report = investigator.investigate_with_report(q)
    
    # Direct tests
    assert "test_rules.py" in ans
    assert "test_benign_ignored" in ans or "test_critical_malware" in ans
    
    # Indirect tests
    assert "test_pipeline.py" in ans
    assert "test_api.py" in ans or "test_ingest_and_list" in ans
    
    # test_release should NOT be in the response
    assert "test_release" not in ans


def test_q6_remediation_switch_impact(investigator):
    """Q6: If AUTO_ISOLATE is set to False, verify what changes and what still happens."""
    q = "If AUTO_ISOLATE is set to False, what changes in critical-incident processing, and which actions still happen?"
    ans, report = investigator.investigate_with_report(q)
    
    # Still happens
    assert "save_incident" in ans
    assert "notify_security_team" in ans
    assert "notify_operations" in ans
    
    # Skipped / changed
    assert "awaiting_approval" in ans
    assert "isolate_host" in ans


def test_q7_recovery_path_and_incident_retention(investigator):
    """Q7: Trace release_host() to audit log. Verify releasing host does NOT delete incident record."""
    q = "Trace the call path from release_host() to the audit log. Does releasing a host delete its incident record?"
    ans, report = investigator.investigate_with_report(q)
    
    assert "release_host -> record_audit" in ans or "restore_host" in ans
    assert "NOT delete" in ans or "not delete" in ans.lower()
    assert "BLOCKED_HOSTS" in ans
    assert "INCIDENTS" in ans


def test_q8_multiple_paths_and_static_vs_dynamic(investigator):
    """Q8: Shortest paths to notify_operations and record_audit, and static vs dynamic explanation."""
    q = "What are the shortest call paths from ingest_alert() to notify_operations() and from ingest_alert() to record_audit()? Explain why shortest graph paths alone do not prove execution for every input."
    ans, report = investigator.investigate_with_report(q)
    
    assert "ingest_alert -> process_event -> open_incident -> notify_operations" in ans
    assert "ingest_alert -> process_event -> record_audit" in ans
    assert "branch" in ans.lower() or "runtime" in ans.lower() or "predicate" in ans.lower()


def test_q9_save_incident_failure(investigator):
    """Q9: If save_incident() fails before returning, downstream operations inside open_incident() are prevented."""
    q = "If save_incident() fails before returning, what downstream operations inside open_incident() are prevented? Which tests are most relevant?"
    ans, report = investigator.investigate_with_report(q)
    
    assert "notify_security_team" in ans
    assert "execute_response" in ans
    assert "notify_operations" in ans
    assert "open_incident" in ans


def test_q10_evidence_honesty_slack(investigator):
    """Q10: Honesty check - verify agent explicitly reports no Slack integration exists."""
    q = "Which function sends a Slack message to the on-call engineer, and what is its exact line number?"
    ans, report = investigator.investigate_with_report(q)
    
    assert "No Slack" in ans or "no Slack" in ans or "no slack" in ans.lower()
    assert "MESSAGES" in ans
    assert "notify_security_team" in ans
    assert report.is_verified is True


def test_q12_repository_isolation(investigator):
    """Q12: Repository isolation check - verify AegisOps does NOT return payment authorization."""
    q = "In AegisOps, which function authorizes customer card payments?"
    ans, report = investigator.investigate_with_report(q)
    
    assert "No Payment" in ans or "no payment" in ans.lower()
    assert "authorize_payment" not in ans
    assert report.is_verified is True
