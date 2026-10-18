"""
app/agents/audit_reviewer.py - AuditReviewerAgent for ADR compliance and code ownership validation.
"""

import time
from typing import Dict, Any, Optional, List
from app.agents.base_agent import BaseAgent
from app.agents.approval import RiskLevel
from app.knowledge.company_brain import CompanyBrain


class AuditReviewerAgent(BaseAgent):
    """
    Audits proposed architectural findings and modifications against organizational policies,
    code ownership rules, and Architectural Decision Records (ADRs).
    """

    def __init__(self, repo_id: str, repo_path: Optional[str] = None, workspace_id: str = "default", approval_gate=None):
        super().__init__(
            role="AuditReviewer",
            repo_id=repo_id,
            repo_path=repo_path,
            workspace_id=workspace_id,
            approval_gate=approval_gate
        )
        self.brain = CompanyBrain(repo_id=repo_id, workspace_id=workspace_id)

    def verify_ownership(self, target_path: str) -> Dict[str, Any]:
        """Resolves team and engineer ownership for a target module/path."""
        return self.brain.answer_company_question(f"Who owns {target_path}?")

    def check_adr_compliance(self, topic_or_question: str) -> Dict[str, Any]:
        """Retrieves authoritative architectural guidance and ADR citations."""
        return self.brain.answer_company_question(topic_or_question)

    def execute_step(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        task_id = f"audit_{int(time.time())}"
        self.record_task(task_id, description=task)

        target_path = (context or {}).get("target_path") or "worker.py"
        adr_topic = (context or {}).get("adr_topic") or "retry policy"

        owner_info = self.verify_ownership(target_path)
        adr_info = self.check_adr_compliance(f"Which architectural decision explains {adr_topic}?")

        citations = owner_info.get("citations", []) + adr_info.get("citations", [])

        action = self.record_action(
            task_id=task_id,
            action_type="AUDIT_COMPLIANCE",
            details={
                "target_path": target_path,
                "owner_found": bool(owner_info.get("answer")),
                "adr_citations": len(citations)
            },
            risk_level=RiskLevel.LOW
        )

        is_approved = len(citations) > 0 or bool(owner_info.get("answer"))

        return {
            "agent_role": self.role,
            "target_path": target_path,
            "ownership": owner_info,
            "adr_guidance": adr_info,
            "citations": citations,
            "is_compliant": is_approved,
            "action": action,
            "status": "COMPLETED"
        }
