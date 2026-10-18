"""
app/agents/base_agent.py - Base Agent Class with Lifecycle and Graph State Recording (ASTERION V3)
"""

import uuid
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from app.graph.client import falkor_client
from app.graph.schema import NodeBase, EdgeBase, NodeType, RelType
from app.agents.approval import ApprovalGate, ApprovalRequest, RiskLevel, ApprovalStatus
from app.memory.manager import GraphMemoryManager

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for specialized agent roles with persistent graph task recording
    and policy approval gates.
    """

    def __init__(
        self,
        role: str,
        repo_id: str,
        repo_path: Optional[str] = None,
        workspace_id: str = "default",
        approval_gate: Optional[ApprovalGate] = None
    ):
        self.role = role
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.workspace_id = workspace_id
        self.agent_id = f"agent_{role.lower()}_{uuid.uuid4().hex[:8]}"
        self.graph_name = f"workspace_{repo_id}"
        self.approval_gate = approval_gate or ApprovalGate()
        self.memory = GraphMemoryManager(repo_id=repo_id, workspace_id=workspace_id)

    def record_task(self, task_id: str, description: str, status: str = "IN_PROGRESS") -> str:
        """Records an AgentTask in the FalkorDB graph."""
        falkor_client.connect()
        node_id = f"task_{self.repo_id}_{task_id}"
        ts = time.time()
        try:
            query = """
            MERGE (t:AgentTask {id: $id})
            SET t.task_id = $task_id,
                t.description = $description,
                t.status = $status,
                t.assigned_role = $role,
                t.claimed_by = $agent_id,
                t.repository_id = $repo_id,
                t.workspace_id = $workspace_id,
                t.updated_at = $ts
            RETURN t.id
            """
            falkor_client.safe_query(self.graph_name, query, {
                "id": node_id,
                "task_id": task_id,
                "description": description,
                "status": status,
                "role": self.role,
                "agent_id": self.agent_id,
                "repo_id": self.repo_id,
                "workspace_id": self.workspace_id,
                "ts": ts
            })
        except Exception as e:
            logger.debug(f"Failed to record AgentTask node: {e}")
        return node_id

    def record_action(
        self,
        task_id: str,
        action_type: str,
        details: Dict[str, Any],
        risk_level: RiskLevel = RiskLevel.LOW
    ) -> Dict[str, Any]:
        """
        Requests approval for the action through the approval gate and records
        the action in the FalkorDB graph.
        """
        approval = self.approval_gate.request_approval(
            action_type=action_type,
            description=details.get("description", action_type),
            risk_level=risk_level,
            payload=details
        )

        falkor_client.connect()
        action_node_id = f"action_{self.repo_id}_{approval.action_id}"
        task_node_id = f"task_{self.repo_id}_{task_id}"
        try:
            act_query = """
            MERGE (a:AgentAction {id: $id})
            SET a.action_id = $action_id,
                a.action_type = $action_type,
                a.risk_level = $risk_level,
                a.status = $status,
                a.agent_id = $agent_id,
                a.repository_id = $repo_id,
                a.timestamp = $ts
            RETURN a.id
            """
            falkor_client.safe_query(self.graph_name, act_query, {
                "id": action_node_id,
                "action_id": approval.action_id,
                "action_type": action_type,
                "risk_level": risk_level.value,
                "status": approval.status.value,
                "agent_id": self.agent_id,
                "repo_id": self.repo_id,
                "ts": time.time()
            })

            # Link task -> action
            link_query = """
            MATCH (t:AgentTask {id: $task_id})
            MATCH (a:AgentAction {id: $action_id})
            MERGE (t)-[:PERFORMED_ACTION]->(a)
            """
            falkor_client.safe_query(self.graph_name, link_query, {
                "task_id": task_node_id,
                "action_id": action_node_id
            })
        except Exception as e:
            logger.debug(f"Failed to record AgentAction node: {e}")

        return {
            "action_id": approval.action_id,
            "status": approval.status.value,
            "is_approved": approval.status in (ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED),
            "approval_request": approval.model_dump()
        }

    @abstractmethod
    def execute_step(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Executes one reasoned step for this agent role."""
        pass
