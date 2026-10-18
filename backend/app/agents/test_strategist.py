"""
app/agents/test_strategist.py - TestStrategistAgent for minimal test selection and execution verification.
"""

import time
from typing import Dict, Any, Optional, List
from app.agents.base_agent import BaseAgent
from app.agents.approval import RiskLevel
from app.agent.actions import AgentActionEngine
from app.services.executor import SafeExecutionEngine, TestExecutionResult


class TestStrategistAgent(BaseAgent):
    """
    Selects test subsets covering changed/impacted symbols and optionally executes
    them inside a sandboxed environment to produce execution receipts.
    """
    __test__ = False

    def __init__(self, repo_id: str, repo_path: Optional[str] = None, approval_gate=None):
        super().__init__(
            role="TestStrategist",
            repo_id=repo_id,
            repo_path=repo_path,
            approval_gate=approval_gate
        )
        self.action_engine = AgentActionEngine(repo_id=repo_id, repo_path=repo_path or ".")
        self.executor = SafeExecutionEngine(prefer_docker=False)

    def select_tests_for_target(self, target_symbol: str) -> List[Dict[str, Any]]:
        """Identifies tests connected to the target symbol via graph traversal."""
        selection = self.action_engine.select_tests_by_graph(target_symbol=target_symbol)
        return selection.get("selected_tests", [])

    def execute_test(self, test_file: str, test_name: Optional[str] = None) -> TestExecutionResult:
        """Executes a test target using SafeExecutionEngine."""
        cwd = self.repo_path or "."
        return self.executor.run_test(test_file, test_name=test_name, cwd=cwd)

    def execute_step(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        task_id = f"test_{int(time.time())}"
        self.record_task(task_id, description=task)

        target = (context or {}).get("target_symbol") or task.split()[-1]
        run_live = (context or {}).get("run_live", False)

        selected_tests = self.select_tests_for_target(target)

        # High risk action if running live code, LOW risk if selecting/dry-run
        risk = RiskLevel.HIGH if run_live else RiskLevel.LOW
        action = self.record_action(
            task_id=task_id,
            action_type="RUN_TESTS" if run_live else "SELECT_TESTS",
            details={
                "target": target,
                "selected_count": len(selected_tests),
                "run_live": run_live
            },
            risk_level=risk
        )

        execution_results = []
        if run_live and action["is_approved"]:
            for t in selected_tests[:3]:
                test_file = t.get("file", t.get("test_id", "").split("::")[0])
                test_name = t.get("name")
                res = self.execute_test(test_file, test_name)
                execution_results.append(res.model_dump())

        return {
            "agent_role": self.role,
            "target": target,
            "selected_tests": selected_tests,
            "execution_results": execution_results,
            "action": action,
            "status": "COMPLETED"
        }
