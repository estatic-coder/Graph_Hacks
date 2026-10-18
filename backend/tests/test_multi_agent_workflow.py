import os
import pytest

from app.agents.approval import ApprovalGate, ApprovalStatus, RiskLevel
from app.agents.code_navigator import CodeNavigatorAgent
from app.agents.impact_evaluator import ImpactEvaluatorAgent
from app.agents.test_strategist import TestStrategistAgent
from app.agents.audit_reviewer import AuditReviewerAgent

@pytest.fixture
def sf_repo_context():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sf_path = os.path.abspath(os.path.join(
        current_dir, "..", "data", "repos", "repo_signalforge_aste_d53975", "SignalForge_ASTERION_Benchmark_3"
    ))
    return {"repo_id": "repo_signalforge_aste_d53975", "repo_path": sf_path}


def test_approval_gate_policies():
    gate = ApprovalGate(require_human_approval=True, auto_approve_max_risk=RiskLevel.LOW)
    
    # 1. Low risk is auto-approved
    req_low = gate.request_approval(
        action_type="READ_FILE",
        description="Reading worker.py source",
        risk_level=RiskLevel.LOW
    )
    assert req_low.status == ApprovalStatus.AUTO_APPROVED

    # 2. High risk is held in PENDING
    req_high = gate.request_approval(
        action_type="MUTATE_CODE",
        description="Overwriting dispatch retry count in worker.py",
        risk_level=RiskLevel.HIGH
    )
    assert req_high.status == ApprovalStatus.PENDING
    assert len(gate.get_pending_requests()) == 1

    # 3. Explicit approval by human
    gate.approve(req_high.action_id, reviewer="lead_architect")
    assert req_high.status == ApprovalStatus.APPROVED
    assert req_high.resolved_by == "lead_architect"
    assert len(gate.get_pending_requests()) == 0

    # 4. Critical risk rejected
    req_crit = gate.request_approval(
        action_type="FORCE_DEPLOY",
        description="Bypassing test suite and deploying",
        risk_level=RiskLevel.CRITICAL
    )
    assert req_crit.status == ApprovalStatus.PENDING
    gate.reject(req_crit.action_id, reviewer="security_officer", reason="Tests did not run")
    assert req_crit.status == ApprovalStatus.REJECTED


def test_code_navigator_step(sf_repo_context):
    nav = CodeNavigatorAgent(repo_id=sf_repo_context["repo_id"], repo_path=sf_repo_context["repo_path"])
    res = nav.execute_step("Locate dispatch symbol", {"target_symbol": "dispatch"})
    assert res["status"] == "COMPLETED"
    assert res["target"] == "dispatch"
    assert "action" in res
    assert res["action"]["is_approved"] is True


def test_impact_evaluator_step(sf_repo_context):
    evaluator = ImpactEvaluatorAgent(repo_id=sf_repo_context["repo_id"], repo_path=sf_repo_context["repo_path"])
    res = evaluator.execute_step("Evaluate impact of dispatch", {"target_symbol": "dispatch"})
    assert res["status"] == "COMPLETED"
    assert "impact" in res
    assert "action" in res


def test_test_strategist_step(sf_repo_context):
    strategist = TestStrategistAgent(repo_id=sf_repo_context["repo_id"], repo_path=sf_repo_context["repo_path"])
    res = strategist.execute_step("Select tests for dispatch", {"target_symbol": "dispatch", "run_live": False})
    assert res["status"] == "COMPLETED"
    assert "selected_tests" in res
    assert res["action"]["is_approved"] is True


def test_audit_reviewer_step(sf_repo_context):
    reviewer = AuditReviewerAgent(repo_id=sf_repo_context["repo_id"], repo_path=sf_repo_context["repo_path"])
    res = reviewer.execute_step("Audit worker.py policies", {"target_path": "worker.py", "adr_topic": "retry policy"})
    assert res["status"] == "COMPLETED"
    assert "ownership" in res
    assert "adr_guidance" in res
    assert len(res["citations"]) > 0


def test_multi_agent_coordination_handoff(sf_repo_context):
    # End-to-end multi-agent orchestration
    gate = ApprovalGate()
    repo_id = sf_repo_context["repo_id"]
    repo_path = sf_repo_context["repo_path"]

    nav = CodeNavigatorAgent(repo_id=repo_id, repo_path=repo_path, approval_gate=gate)
    impact = ImpactEvaluatorAgent(repo_id=repo_id, repo_path=repo_path, approval_gate=gate)
    strat = TestStrategistAgent(repo_id=repo_id, repo_path=repo_path, approval_gate=gate)
    audit = AuditReviewerAgent(repo_id=repo_id, repo_path=repo_path, approval_gate=gate)

    # 1. Navigator finds target
    nav_res = nav.execute_step("Find dispatch", {"target_symbol": "dispatch"})
    assert nav_res["status"] == "COMPLETED"

    # 2. Impact analyzes risk
    impact_res = impact.execute_step("Assess dispatch", {"target_symbol": nav_res["target"]})
    assert impact_res["status"] == "COMPLETED"

    # 3. Test strategist selects tests
    test_res = strat.execute_step("Select tests", {"target_symbol": nav_res["target"], "run_live": False})
    assert test_res["status"] == "COMPLETED"

    # 4. Audit reviewer verifies policy
    audit_res = audit.execute_step("Audit policy", {"target_path": "signalforge/worker.py", "adr_topic": "retry policy"})
    assert audit_res["status"] == "COMPLETED"
    assert len(audit_res["citations"]) > 0
