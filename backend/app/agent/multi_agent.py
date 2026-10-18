"""
app/agent/multi_agent.py - Multi-Agent Engineering Investigation System backed by FalkorDB.

Implements 4 specialized engineering investigation roles:
1. Graph Investigator (Symbol resolution, dependency traversal, algorithm selection)
2. Execution Analyst (Branch analysis, loop/retry simulation, state transitions, crash consistency)
3. Test and Impact Analyst (Affected code, test selection, regression predictions)
4. Evidence Reviewer (Citation audit, graph path validation, contradiction detection, approval/rejection)

Coordinates through shared FalkorDB investigation state, bounded task leases,
explicit handoff records, and cross-session continuation.
"""

import os
import time
import uuid
import logging
from enum import Enum
from typing import Dict, List, Any, Optional

from app.graph.client import falkor_client
from app.graph.schema import NodeType, RelType
from app.graph.algorithms import GraphAlgorithmEngine
from app.agent.control_flow import ControlFlowAnalyzer
from app.agent.actions import AgentActionEngine
from app.agent.verifier import CrossSectionValidator

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    GRAPH_INVESTIGATOR = "GraphInvestigator"
    EXECUTION_ANALYST = "ExecutionAnalyst"
    TEST_IMPACT_ANALYST = "TestImpactAnalyst"
    EVIDENCE_REVIEWER = "EvidenceReviewer"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class HandoffRecord:
    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        task_id: str,
        context: Dict[str, Any],
        timestamp: float
    ):
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.task_id = task_id
        self.context = context
        self.timestamp = timestamp

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "task_id": self.task_id,
            "context": self.context,
            "timestamp": self.timestamp
        }


class MultiAgentInvestigation:
    """
    Shared investigation state stored in FalkorDB and synchronized across agent roles.
    """

    def __init__(
        self,
        investigation_id: str,
        objective: str,
        repo_id: str,
        repo_path: str,
        workspace_id: str = "default"
    ):
        self.investigation_id = investigation_id
        self.objective = objective
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.workspace_id = workspace_id
        self.graph_name = f"workspace_{repo_id}"
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.handoffs: List[HandoffRecord] = []
        self.evidence_pool: List[Dict[str, Any]] = []
        self.conclusions: List[Dict[str, Any]] = []
        self.status = "ACTIVE"
        self._sync_to_graph()

    def _sync_to_graph(self):
        """Persists the Investigation root node in FalkorDB."""
        if not falkor_client.check_health():
            return
        cypher = """
        MERGE (inv:Investigation {id: $id})
        SET inv.objective = $objective,
            inv.repository_id = $repo_id,
            inv.workspace_id = $workspace_id,
            inv.status = $status,
            inv.created_at = $ts
        """
        try:
            falkor_client.safe_query(self.graph_name, cypher, {
                "id": self.investigation_id,
                "objective": self.objective,
                "repo_id": self.repo_id,
                "workspace_id": self.workspace_id,
                "status": self.status,
                "ts": time.time()
            })
        except Exception as e:
            logger.debug(f"Investigation graph sync: {e}")

    def add_task(self, task_id: str, description: str, role: AgentRole) -> Dict[str, Any]:
        task = {
            "task_id": task_id,
            "description": description,
            "assigned_role": role.value,
            "status": TaskStatus.PENDING.value,
            "claimed_by": None,
            "lease_expires": 0.0,
            "result": None
        }
        self.tasks[task_id] = task

        # Persist task in FalkorDB
        if falkor_client.check_health():
            cypher = """
            MATCH (inv:Investigation {id: $inv_id})
            MERGE (t:AgentTask {id: $task_id})
            SET t.description = $desc,
                t.assigned_role = $role,
                t.status = $status
            MERGE (inv)-[:CONTAINS]->(t)
            """
            try:
                falkor_client.safe_query(self.graph_name, cypher, {
                    "inv_id": self.investigation_id,
                    "task_id": task_id,
                    "desc": description,
                    "role": role.value,
                    "status": TaskStatus.PENDING.value
                })
            except Exception as e:
                logger.debug(f"Task graph sync: {e}")

        return task

    def claim_task(self, task_id: str, agent_id: str, lease_duration_sec: float = 30.0) -> bool:
        """
        Concurrency control: atomic bounded task lease prevents duplicate work across agents.
        """
        now = time.time()
        lease_exp = now + lease_duration_sec

        # 1. Atomic FalkorDB lease check & update
        if falkor_client.check_health():
            atomic_cypher = """
            MATCH (t:AgentTask {id: $task_id})
            WHERE t.status = 'PENDING' OR t.lease_expires <= $now OR t.claimed_by = $agent_id
            SET t.status = $status,
                t.claimed_by = $agent_id,
                t.claim_timestamp = $claim_ts,
                t.lease_expires = $lease_exp
            RETURN t.id
            """
            try:
                res = falkor_client.safe_query(self.graph_name, atomic_cypher, {
                    "task_id": task_id,
                    "status": TaskStatus.IN_PROGRESS.value,
                    "agent_id": agent_id,
                    "claim_ts": now,
                    "lease_exp": lease_exp,
                    "now": now
                })
                if not (res and res.result_set and len(res.result_set) > 0):
                    # Lease already held by another agent in FalkorDB
                    return False
            except Exception as e:
                logger.debug(f"Atomic lease claim query error: {e}")

        # 2. Update local in-memory task dictionary
        task = self.tasks.get(task_id)
        if not task:
            task = {
                "task_id": task_id,
                "description": "",
                "assigned_role": AgentRole.EXECUTION_ANALYST.value,
                "status": TaskStatus.PENDING.value,
                "claimed_by": None,
                "lease_expires": 0.0,
                "result": None
            }
            self.tasks[task_id] = task

        # Enforce in-memory lease concurrency control
        if task.get("claimed_by") and task.get("claimed_by") != agent_id:
            if now < task.get("lease_expires", 0.0):
                return False

        task["status"] = TaskStatus.IN_PROGRESS.value
        task["claimed_by"] = agent_id
        task["claim_timestamp"] = now
        task["lease_expires"] = lease_exp

        return True

    def record_handoff(
        self,
        from_agent: str,
        to_agent: str,
        task_id: str,
        context: Dict[str, Any]
    ) -> HandoffRecord:
        """Records explicit agent handoff in memory and FalkorDB."""
        rec = HandoffRecord(
            from_agent=from_agent,
            to_agent=to_agent,
            task_id=task_id,
            context=context,
            timestamp=time.time()
        )
        self.handoffs.append(rec)

        if falkor_client.check_health():
            cypher = """
            MATCH (inv:Investigation {id: $inv_id})
            MERGE (a1:Agent {id: $from_agent})
            MERGE (a2:Agent {id: $to_agent})
            MERGE (a1)-[r:HANDOFF_TO {task_id: $task_id, timestamp: $ts}]->(a2)
            """
            try:
                falkor_client.safe_query(self.graph_name, cypher, {
                    "inv_id": self.investigation_id,
                    "from_agent": from_agent,
                    "to_agent": to_agent,
                    "task_id": task_id,
                    "ts": rec.timestamp
                })
            except Exception:
                pass

        return rec

    def complete_task(self, task_id: str, result: Dict[str, Any]):
        task = self.tasks.get(task_id)
        if task:
            task["status"] = TaskStatus.COMPLETED.value
            task["result"] = result
            if "evidence" in result:
                self.evidence_pool.extend(result["evidence"] if isinstance(result["evidence"], list) else [result["evidence"]])
            if falkor_client.check_health():
                try:
                    falkor_client.safe_query(self.graph_name, "MATCH (t:AgentTask {id: $task_id}) SET t.status = 'COMPLETED'", {"task_id": task_id})
                except Exception:
                    pass


class MultiAgentInvestigationCoordinator:
    """
    Coordinates execution of the 4 specialized agent roles across a shared investigation.
    """

    def __init__(self, repo_id: str, repo_path: str, workspace_id: str = "default"):
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.workspace_id = workspace_id
        self.active_investigations: Dict[str, MultiAgentInvestigation] = {}

    def start_investigation(self, objective: str, investigation_id: Optional[str] = None) -> MultiAgentInvestigation:
        inv_id = investigation_id or f"inv_{uuid.uuid4().hex[:8]}"
        inv = MultiAgentInvestigation(
            investigation_id=inv_id,
            objective=objective,
            repo_id=self.repo_id,
            repo_path=self.repo_path,
            workspace_id=self.workspace_id
        )
        self.active_investigations[inv_id] = inv
        return inv

    def get_investigation(self, investigation_id: str) -> Optional[MultiAgentInvestigation]:
        return self.active_investigations.get(investigation_id)

    def resume_investigation(self, investigation_id: str) -> Optional[MultiAgentInvestigation]:
        """
        Retrieves and reconstructs an investigation session from FalkorDB, allowing
        cross-process or post-restart continuation by other agent instances.
        """
        if investigation_id in self.active_investigations:
            return self.active_investigations[investigation_id]

        if falkor_client.check_health():
            cypher = """
            MATCH (inv:Investigation {id: $id})
            RETURN inv.objective, inv.repository_id, inv.workspace_id, inv.status
            """
            try:
                res = falkor_client.safe_query(f"workspace_{self.repo_id}", cypher, {"id": investigation_id})
                if res and res.result_set:
                    row = res.result_set[0]
                    obj = row[0] or ""
                    r_id = row[1] or self.repo_id
                    ws_id = row[2] or self.workspace_id
                    st = row[3] or "ACTIVE"

                    inv = MultiAgentInvestigation(
                        investigation_id=investigation_id,
                        objective=obj,
                        repo_id=r_id,
                        repo_path=self.repo_path,
                        workspace_id=ws_id
                    )
                    inv.status = st

                    # Retrieve tasks from FalkorDB
                    task_cypher = """
                    MATCH (inv:Investigation {id: $id})-[:CONTAINS]->(t:AgentTask)
                    RETURN t.id, t.description, t.assigned_role, t.status, t.claimed_by, t.lease_expires
                    """
                    t_res = falkor_client.safe_query(f"workspace_{self.repo_id}", task_cypher, {"id": investigation_id})
                    if t_res and t_res.result_set:
                        for t_row in t_res.result_set:
                            t_id, desc, role, status, claimed, lease = t_row[0], t_row[1], t_row[2], t_row[3], t_row[4], t_row[5]
                            inv.tasks[t_id] = {
                                "task_id": t_id,
                                "description": desc or "",
                                "assigned_role": role or AgentRole.GRAPH_INVESTIGATOR.value,
                                "status": status or TaskStatus.PENDING.value,
                                "claimed_by": claimed,
                                "lease_expires": float(lease or 0.0),
                                "result": None
                            }
                    self.active_investigations[investigation_id] = inv
                    return inv
            except Exception as e:
                logger.error(f"Failed to resume investigation {investigation_id} from FalkorDB: {e}")
        return None

    # -------------------------------------------------------------------------
    # Role 1: Graph Investigator
    # -------------------------------------------------------------------------
    def run_graph_investigator(
        self,
        investigation: MultiAgentInvestigation,
        target_symbol: str
    ) -> Dict[str, Any]:
        task_id = f"task_graph_{target_symbol}"
        investigation.add_task(task_id, f"Analyze graph relationships for {target_symbol}", AgentRole.GRAPH_INVESTIGATOR)
        agent_id = "agent_graph_investigator_1"
        assert investigation.claim_task(task_id, agent_id), "Failed to claim task"

        engine = GraphAlgorithmEngine(repo_id=self.repo_id)
        # Select best algorithm based on objective
        if "dependency" in investigation.objective.lower() or "reach" in investigation.objective.lower():
            algo_res = engine.reachable_nodes(target_symbol, max_depth=3)
        else:
            algo_res = engine.reverse_dependencies(target_symbol, max_depth=3)

        result = {
            "role": AgentRole.GRAPH_INVESTIGATOR.value,
            "target_symbol": target_symbol,
            "algorithm_used": algo_res.algorithm,
            "rationale": algo_res.rationale,
            "discovered_nodes": algo_res.result.get("nodes", []),
            "node_count": algo_res.result.get("count", 0),
            "evidence": {
                "type": "GRAPH_REACHABILITY",
                "symbol": target_symbol,
                "connected_components": algo_res.result.get("nodes", [])
            }
        }
        investigation.complete_task(task_id, result)
        return result

    # -------------------------------------------------------------------------
    # Role 2: Execution Analyst
    # -------------------------------------------------------------------------
    def run_execution_analyst(
        self,
        investigation: MultiAgentInvestigation,
        scenario_question: str
    ) -> Dict[str, Any]:
        task_id = f"task_exec_{uuid.uuid4().hex[:6]}"
        investigation.add_task(task_id, f"Simulate execution semantics for scenario", AgentRole.EXECUTION_ANALYST)
        agent_id = "agent_execution_analyst_1"
        assert investigation.claim_task(task_id, agent_id), "Failed to claim task"

        cfa = ControlFlowAnalyzer(repo_path=self.repo_path)
        scenario_res = cfa.evaluate_scenario(scenario_question)

        result = {
            "role": AgentRole.EXECUTION_ANALYST.value,
            "scenario": scenario_res.get("scenario", "generic_execution"),
            "calculated_attempts": scenario_res.get("calculated_attempts"),
            "final_status": scenario_res.get("final_status") or scenario_res.get("status"),
            "summary": scenario_res.get("summary", ""),
            "citations": scenario_res.get("citations", []),
            "evidence": {
                "type": "EXECUTION_TRACE",
                "scenario": scenario_res.get("scenario"),
                "citations": scenario_res.get("citations", [])
            }
        }
        investigation.complete_task(task_id, result)
        return result

    # -------------------------------------------------------------------------
    # Role 3: Test and Impact Analyst
    # -------------------------------------------------------------------------
    def run_test_impact_analyst(
        self,
        investigation: MultiAgentInvestigation,
        target_symbol: str
    ) -> Dict[str, Any]:
        task_id = f"task_test_{target_symbol}"
        investigation.add_task(task_id, f"Select tests covering {target_symbol}", AgentRole.TEST_IMPACT_ANALYST)
        agent_id = "agent_test_analyst_1"
        assert investigation.claim_task(task_id, agent_id), "Failed to claim task"

        actions = AgentActionEngine(repo_id=self.repo_id, repo_path=self.repo_path, workspace_id=self.workspace_id)
        selection = actions.select_tests_by_graph(target_symbol=target_symbol, max_graph_distance=3)

        result = {
            "role": AgentRole.TEST_IMPACT_ANALYST.value,
            "target_symbol": target_symbol,
            "selected_test_count": len(selection["selected_tests"]),
            "selected_tests": [t["test_id"] for t in selection["selected_tests"]],
            "top_reasons": [t["reasons"] for t in selection["selected_tests"][:3]],
            "evidence": {
                "type": "TEST_COVERAGE",
                "target": target_symbol,
                "tests": [t["test_id"] for t in selection["selected_tests"]]
            }
        }
        investigation.complete_task(task_id, result)
        return result

    # -------------------------------------------------------------------------
    # Role 4: Evidence Reviewer
    # -------------------------------------------------------------------------
    def run_evidence_reviewer(
        self,
        investigation: MultiAgentInvestigation,
        proposed_conclusion: str,
        citations: List[str]
    ) -> Dict[str, Any]:
        task_id = f"task_review_{uuid.uuid4().hex[:6]}"
        investigation.add_task(task_id, "Audit citations and verify evidence", AgentRole.EVIDENCE_REVIEWER)
        agent_id = "agent_evidence_reviewer_1"
        assert investigation.claim_task(task_id, agent_id), "Failed to claim task"

        validator = CrossSectionValidator(repo_id=self.repo_id, repo_path=self.repo_path)
        valid_citations = []
        invalid_citations = []

        for cit in citations:
            parts = cit.split(":")
            if parts and os.path.exists(os.path.join(self.repo_path, parts[0])):
                valid_citations.append(cit)
            else:
                invalid_citations.append(cit)

        reconciled_text, issues = validator.validate_and_reconcile(proposed_conclusion)
        has_contradictions = any("CONTRADICTION" in str(iss).upper() for iss in issues) or ("CONTRADICTION" in proposed_conclusion.upper())
        if "CONTRADICTION" in proposed_conclusion.upper() and not any("CONTRADICTION" in str(iss).upper() for iss in issues):
            issues.append("Unresolved contradiction detected in conclusion text")
        is_approved = (len(invalid_citations) == 0) and (not has_contradictions)

        result = {
            "role": AgentRole.EVIDENCE_REVIEWER.value,
            "is_approved": is_approved,
            "valid_citations": valid_citations,
            "invalid_citations": invalid_citations,
            "detected_issues": [str(i) for i in issues],
            "verified_conclusion": reconciled_text,
            "decision": "APPROVED" if is_approved else "REJECTED_NEEDS_REVISION"
        }
        investigation.complete_task(task_id, result)
        return result

    # -------------------------------------------------------------------------
    # End-to-End Orchestrated Pipeline Across All 4 Roles
    # -------------------------------------------------------------------------
    def execute_collaborative_investigation(
        self,
        objective: str,
        target_symbol: str,
        scenario_question: str
    ) -> Dict[str, Any]:
        """
        Executes a 4-agent collaborative investigation:
        1. Graph Investigator maps dependencies.
        2. Handoff to Execution Analyst to simulate state and loops.
        3. Handoff to Test Analyst to select regression tests.
        4. Handoff to Evidence Reviewer to audit and approve findings.
        """
        inv = self.start_investigation(objective=objective)

        # Step 1: Graph Investigator
        graph_findings = self.run_graph_investigator(inv, target_symbol=target_symbol)
        inv.record_handoff(
            from_agent="agent_graph_investigator_1",
            to_agent="agent_execution_analyst_1",
            task_id="task_graph_handoff",
            context={"target_symbol": target_symbol, "nodes": graph_findings["discovered_nodes"]}
        )

        # Step 2: Execution Analyst
        exec_findings = self.run_execution_analyst(inv, scenario_question=scenario_question)
        inv.record_handoff(
            from_agent="agent_execution_analyst_1",
            to_agent="agent_test_analyst_1",
            task_id="task_exec_handoff",
            context={"status": exec_findings["final_status"], "scenario": exec_findings["scenario"]}
        )

        # Step 3: Test and Impact Analyst
        test_findings = self.run_test_impact_analyst(inv, target_symbol=target_symbol)
        inv.record_handoff(
            from_agent="agent_test_analyst_1",
            to_agent="agent_evidence_reviewer_1",
            task_id="task_test_handoff",
            context={"tests": test_findings["selected_tests"]}
        )

        # Step 4: Evidence Reviewer
        citations = exec_findings.get("citations", [])
        proposed = f"Target '{target_symbol}' results in status '{exec_findings.get('final_status')}'. Covered by {len(test_findings['selected_tests'])} test(s)."
        review_result = self.run_evidence_reviewer(inv, proposed_conclusion=proposed, citations=citations)

        # Verify cross-session continuation: simulate genuinely independent agent instance resuming from FalkorDB
        resumed_inv = None
        try:
            fresh_coordinator = MultiAgentInvestigationCoordinator(repo_id=self.repo_id, repo_path=self.repo_path, workspace_id=self.workspace_id)
            resumed_inv = fresh_coordinator.resume_investigation(inv.investigation_id)
        except Exception as e:
            logger.debug(f"Cross-session resumption check: {e}")

        distinct_agents = [
            "agent_graph_investigator_1",
            "agent_execution_analyst_1",
            "agent_test_analyst_1",
            "agent_evidence_reviewer_1"
        ]

        task_records = []
        for t_id, t_info in inv.tasks.items():
            task_records.append({
                "task_id": t_id,
                "role": t_info.get("assigned_role"),
                "claimed_by": t_info.get("claimed_by"),
                "claim_timestamp": t_info.get("claim_timestamp"),
                "lease_expires": t_info.get("lease_expires"),
                "status": t_info.get("status"),
                "description": t_info.get("description")
            })

        handoff_records = [h.to_dict() for h in inv.handoffs]

        return {
            "investigation_id": inv.investigation_id,
            "objective": objective,
            "distinct_agents": distinct_agents,
            "tasks": task_records,
            "handoffs": handoff_records,
            "completed_tasks": len([t for t in inv.tasks.values() if t["status"] == TaskStatus.COMPLETED.value]),
            "handoff_count": len(inv.handoffs),
            "evidence_count": len(inv.evidence_pool),
            "graph_findings": graph_findings,
            "execution_findings": exec_findings,
            "test_findings": test_findings,
            "reviewer_result": review_result,
            "final_approved": review_result["is_approved"],
            "cross_session_continuation_verified": bool(resumed_inv is not None and len(resumed_inv.tasks) > 0)
        }
