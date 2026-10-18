"""
app/agents/impact_evaluator.py - ImpactEvaluatorAgent for blast radius and dependency risk analysis.
"""

import time
import dataclasses
from typing import Dict, Any, Optional, List
from app.agents.base_agent import BaseAgent
from app.agents.approval import RiskLevel
from app.agent.impact import ImpactAnalyzer


class ImpactEvaluatorAgent(BaseAgent):
    """
    Evaluates proposed changes, computes multi-hop reverse dependency chains,
    and quantifies downstream risk levels.
    """

    def __init__(self, repo_id: str, repo_path: Optional[str] = None, approval_gate=None):
        super().__init__(
            role="ImpactEvaluator",
            repo_id=repo_id,
            repo_path=repo_path,
            approval_gate=approval_gate
        )
        self.analyzer = ImpactAnalyzer(repo_id=repo_id, repo_path=repo_path)

    def evaluate_symbol_impact(self, symbol_name: str) -> Dict[str, Any]:
        """Calculates downstream blast radius for a given symbol."""
        res = self.analyzer.analyze_symbol_impact(symbol_name)
        if dataclasses.is_dataclass(res):
            return dataclasses.asdict(res)
        if hasattr(res, "model_dump"):
            return res.model_dump()
        return dict(res)

    def execute_step(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        task_id = f"impact_{int(time.time())}"
        self.record_task(task_id, description=task)

        target = (context or {}).get("target_symbol") or task.split()[-1]
        impact_result = self.evaluate_symbol_impact(target)

        risk_level = RiskLevel.HIGH if impact_result.get("risk_level") == "HIGH" else RiskLevel.MEDIUM
        action = self.record_action(
            task_id=task_id,
            action_type="EVALUATE_IMPACT",
            details={
                "target": target,
                "dependents_count": impact_result.get("total_dependents", 0),
                "risk_level": impact_result.get("risk_level", "LOW")
            },
            risk_level=risk_level
        )

        return {
            "agent_role": self.role,
            "target": target,
            "impact": impact_result,
            "action": action,
            "status": "COMPLETED"
        }
