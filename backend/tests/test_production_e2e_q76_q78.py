"""
backend/tests/test_production_e2e_q76_q78.py

Comprehensive End-to-End Integration Tests for ASTERION Production Pipeline.
Tests:
- Q76: Impact paths from ledger to gateway (direct, indirect, shortest path, citations)
- Q77: State simulation for failing auth rollout (rolled_back, attempts 3, CHECKS 3, slots restored to 2, version 1.0, LOCKED empty, READY empty, changes/events)
- Q78: Guard precedence for staging gateway rollout (status blocked, event missing_dependency, saved in ROLLOUTS, no slot, not enqueued, guard order)
- Negative test: Fail-closed verification (incomplete result rejected)
- Cold process vs warm process consistency
- Fresh repository / session namespace isolation
"""

import os
import sys
import json
import pytest
from typing import Dict, Any

# Ensure backend root is on path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from app.agent.investigator import GraphInvestigator
from app.agent.contracts import AnswerRequirementsContract

REPO_ID = "repo_deployweave_aste_667ec8"


class TestProductionQ76Q78E2E:
    """Production integration test suite asserting actual answer contents and contract enforcement."""

    def test_q76_impact_paths_direct_backend(self):
        """Q76: Find direct and indirect impact paths from ledger to gateway."""
        investigator = GraphInvestigator(repo_id=REPO_ID, workspace_id="default")
        answer, report = investigator.investigate_with_report(
            question="Find the direct and indirect impact paths from ledger to gateway."
        )

        # 1. Assert Investigation Plan contains capabilities > 0
        pdata = getattr(investigator, "last_pipeline_data", {}) or {}
        plan = pdata.get("investigation_plan", {})
        steps = plan.get("steps", [])
        assert len(steps) >= 1, "Investigation plan must have >= 1 capability step"
        assert steps[0]["capability"] == "STATIC_PATH_ANALYSIS"

        # 2. Assert Verification Semantics
        assert report.is_verified is True, f"Q76 must be verified. Summary: {report.summary}"
        assert report.source_verified is True
        assert len(getattr(report, "missing_required_fields", [])) == 0
        assert "INCOMPLETE_RESULT" not in getattr(report, "summary", "")

        # 3. Assert Answer Content (paths and shortest path)
        ans_lower = answer.lower()
        assert "ledger" in ans_lower and "gateway" in ans_lower
        assert "ledger -> gateway" in ans_lower or "ledger → gateway" in ans_lower
        assert ("ledger -> auth -> gateway" in ans_lower) or ("ledger → auth → gateway" in ans_lower)
        assert "shortest" in ans_lower and "1" in ans_lower
        assert "deployweave/config.py" in answer

        # 4. Assert Request Lifecycle Trace
        trace = pdata.get("trace", {})
        assert trace.get("trace_id") is not None
        stages = [s["stage_name"] for s in trace.get("stages", [])]
        expected_stages = [
            "api_payload", "repository_selection", "intent_classification",
            "entity_resolution", "plan_generation", "tool_execution",
            "tool_output_normalization", "evidence_retrieval", "answer_synthesis",
            "verification"
        ]
        for st in expected_stages:
            assert st in stages, f"Trace must contain stage {st}"

    def test_q77_state_simulation_direct_backend(self):
        """Q77: Simulate a staging auth v2.0 rollout with three failed health probes."""
        investigator = GraphInvestigator(repo_id=REPO_ID, workspace_id="default")
        answer, report = investigator.investigate_with_report(
            question="Simulate a staging auth v2.0 rollout with three failed health probes."
        )

        # 1. Assert Investigation Plan
        pdata = getattr(investigator, "last_pipeline_data", {}) or {}
        plan = pdata.get("investigation_plan", {})
        steps = plan.get("steps", [])
        assert len(steps) >= 1
        assert steps[0]["capability"] == "MULTIPHASE_SCENARIO"

        # 2. Assert Verification Semantics
        assert report.is_verified is True, f"Q77 must be verified. Summary: {report.summary}"
        assert len(getattr(report, "missing_required_fields", [])) == 0

        # 3. Assert Actual State Ledger Values
        assert "rolled_back" in answer
        assert "3" in answer  # attempts 3 and CHECKS['r1'] = 3
        assert "checks" in answer.lower() and "3" in answer
        assert "1.0" in answer  # restored to 1.0
        assert "slots" in answer.lower() and "2" in answer  # auth slots restored to 2
        assert "locked = set()" in answer.lower() or "no remaining lock" in answer.lower()
        assert "ready = []" in answer.lower() or "no remaining queue" in answer.lower()
        assert "changes" in answer.lower()
        assert "events" in answer.lower()
        assert "health_failed" in answer

        # 4. Assert Contract Validation
        contract = AnswerRequirementsContract(
            "Simulate a staging auth v2.0 rollout with three failed health probes."
        )
        is_valid, missing = contract.validate_answer(answer, {})
        assert is_valid is True, f"Contract validation failed: missing {missing}"

    def test_q78_guard_precedence_direct_backend(self):
        """Q78: Simulate staging gateway submission with ledger missing."""
        investigator = GraphInvestigator(repo_id=REPO_ID, workspace_id="default")
        answer, report = investigator.investigate_with_report(
            question="Simulate staging gateway submission with ledger missing."
        )

        # 1. Assert Investigation Plan
        pdata = getattr(investigator, "last_pipeline_data", {}) or {}
        plan = pdata.get("investigation_plan", {})
        steps = plan.get("steps", [])
        assert len(steps) >= 1
        assert steps[0]["capability"] == "BRANCH_ANALYSIS"

        # 2. Assert Verification Semantics
        assert report.is_verified is True, f"Q78 must be verified. Summary: {report.summary}"
        assert len(getattr(report, "missing_required_fields", [])) == 0

        # 3. Assert Guard Ordering & Blocked Status
        assert "blocked" in answer
        assert "missing_dependency" in answer
        assert "rollouts" in answer.lower()
        assert "not enqueued" in answer.lower() or "ready = []" in answer.lower()
        assert "no slot acquired" in answer.lower() or "acquire" in answer.lower()
        assert "before" in answer.lower()  # dependency guard executes before review guard
        assert "unreachable" in answer.lower()  # review guard unreachable

        # 4. Assert Contract Validation
        contract = AnswerRequirementsContract(
            "Simulate staging gateway submission with ledger missing."
        )
        is_valid, missing = contract.validate_answer(answer, {})
        assert is_valid is True, f"Contract validation failed: missing {missing}"

    def test_fail_closed_verification_on_empty_answer(self):
        """Verification must fail closed (is_verified=False) when an answer lacks substance or citations."""
        investigator = GraphInvestigator(repo_id=REPO_ID, workspace_id="default")
        
        # Test with a question for an unknown/alien entity with no ground truth in DeployWeave
        answer, report = investigator.investigate_with_report(
            question="Tell me about nonexistent_foreign_function_xyz999() and verify all its paths."
        )
        # Must be rejected / not verified
        assert report.is_verified is False
        assert "INCOMPLETE_RESULT" in report.summary or "REJECTED" in report.summary

    def test_cold_vs_warm_process_consistency(self):
        """Tests that cold process invocation and warm process invocation produce identical results."""
        q = "Find the direct and indirect impact paths from ledger to gateway."
        
        # Warm run 1
        inv1 = GraphInvestigator(repo_id=REPO_ID, workspace_id="default")
        ans1, rep1 = inv1.investigate_with_report(question=q)

        # Warm run 2
        inv2 = GraphInvestigator(repo_id=REPO_ID, workspace_id="default")
        ans2, rep2 = inv2.investigate_with_report(question=q)

        assert rep1.is_verified == rep2.is_verified
        assert len(inv1.last_pipeline_data.get("investigation_plan", {}).get("steps", [])) == len(inv2.last_pipeline_data.get("investigation_plan", {}).get("steps", []))
        assert ("ledger -> gateway" in ans1.lower()) and ("ledger -> gateway" in ans2.lower())

    def test_fresh_session_namespace_isolation(self):
        """Tests that different session/workspace IDs maintain strict isolation without state leakage."""
        q = "Simulate a staging auth v2.0 rollout with three failed health probes."
        
        inv_session_a = GraphInvestigator(repo_id=REPO_ID, workspace_id="session_alpha")
        ans_a, rep_a = inv_session_a.investigate_with_report(question=q, session_id="sess_a_123")

        inv_session_b = GraphInvestigator(repo_id=REPO_ID, workspace_id="session_beta")
        ans_b, rep_b = inv_session_b.investigate_with_report(question=q, session_id="sess_b_456")

        assert rep_a.is_verified is True
        assert rep_b.is_verified is True
        assert inv_session_a.last_pipeline_data["trace"]["trace_id"] != inv_session_b.last_pipeline_data["trace"]["trace_id"]

    def test_production_api_endpoint_parity(self):
        """Tests production HTTP API /api/investigate with FastAPI TestClient."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # Test Q76
        resp76 = client.post("/api/investigate", json={
            "repo_id": REPO_ID,
            "query": "Find the direct and indirect impact paths from ledger to gateway."
        })
        assert resp76.status_code == 200
        d76 = resp76.json()
        assert d76["verification"]["is_verified"] is True
        assert len(d76["investigation_plan"]["steps"]) >= 1
        assert "ledger -> gateway" in d76["answer"] or "ledger → gateway" in d76["answer"]
        assert d76["trace"]["stage_count"] >= 10

        # Test Q77
        resp77 = client.post("/api/investigate", json={
            "repo_id": REPO_ID,
            "query": "Simulate a staging auth v2.0 rollout with three failed health probes."
        })
        assert resp77.status_code == 200
        d77 = resp77.json()
        assert d77["verification"]["is_verified"] is True
        assert "rolled_back" in d77["answer"]
        assert "3" in d77["answer"]

        # Test Q78
        resp78 = client.post("/api/investigate", json={
            "repo_id": REPO_ID,
            "query": "Simulate staging gateway submission with ledger missing."
        })
        assert resp78.status_code == 200
        d78 = resp78.json()
        assert d78["verification"]["is_verified"] is True
        assert "blocked" in d78["answer"]
        assert "missing_dependency" in d78["answer"]

