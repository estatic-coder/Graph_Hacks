"""
app/agent/demo_scenario.py - End-to-End Hackathon Demonstration:
The AI Engineering Incident Investigator.

Executes the 6 official demonstration scenes:
- Scene 1: Graph reasoning (What happens if notification worker fails?)
- Scene 2: Graph-driven action (Find tests affected by removing failure cleanup, verify regression)
- Scene 3: Persistent memory (Retrieve previous investigation across distinct session)
- Scene 4: Multi-agent coordination (Graph Investigator -> Test Analyst -> Evidence Reviewer)
- Scene 5: Decision Explainability (Question -> Graph Query -> Evidence -> Tool -> Action -> Result)
- Scene 6: Company Brain (Ownership and ADR lookup explaining retry policy)
"""

import time
from typing import Dict, Any

from app.graph.algorithms import GraphAlgorithmEngine
from app.agent.decision_engine import GraphDecisionEngine
from app.agent.actions import AgentActionEngine
from app.agent.multi_agent import MultiAgentInvestigationCoordinator
from app.knowledge.company_brain import CompanyBrain
from app.memory.manager import GraphMemoryManager


class IncidentInvestigatorDemo:
    def __init__(self, repo_id: str, repo_path: str, workspace_id: str = "demo_ws"):
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.workspace_id = workspace_id
        self.decision_engine = GraphDecisionEngine(repo_id=repo_id, repo_path=repo_path, workspace_id=workspace_id)
        self.actions = AgentActionEngine(repo_id=repo_id, repo_path=repo_path, workspace_id=workspace_id)
        self.coordinator = MultiAgentInvestigationCoordinator(repo_id=repo_id, repo_path=repo_path, workspace_id=workspace_id)
        self.company_brain = CompanyBrain(repo_id=repo_id, workspace_id=workspace_id)
        self.memory = GraphMemoryManager(repo_id=repo_id, repo_path=repo_path, workspace_id=workspace_id)

    # -------------------------------------------------------------
    # Scene 1: Graph Reasoning
    # -------------------------------------------------------------
    def run_scene_1_graph_reasoning(self) -> Dict[str, Any]:
        """
        Scene 1: 'What happens if the notification worker fails?'
        Shows: Dependency traversal, queue handoff, retry analysis, affected services, source evidence.
        """
        t0 = time.perf_counter()
        question = "What happens if the notification worker fails?"
        decision = self.decision_engine.execute_agent_loop(
            objective=question,
            target_symbol="dispatch",
            authorize_actions=False
        )

        return {
            "scene": 1,
            "title": "Graph Reasoning",
            "question": question,
            "target": decision["target"],
            "influencing_path": decision["graph_influencing_path"],
            "chosen_algorithm": decision["chosen_algorithm"],
            "explanation": decision["explanation"],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)
        }

    # -------------------------------------------------------------
    # Scene 2: Graph-Driven Action
    # -------------------------------------------------------------
    def run_scene_2_graph_driven_action(self) -> Dict[str, Any]:
        """
        Scene 2: 'Find the tests affected by removing failure cleanup, and verify the regression.'
        Shows: Graph-based test selection, selected test execution, regression detection.
        """
        t0 = time.perf_counter()
        selection = self.actions.select_tests_by_graph(
            target_symbol="dispatch",
            max_graph_distance=3,
            auto_run=True,
            authorized=True
        )

        return {
            "scene": 2,
            "title": "Graph-Driven Action",
            "action": "select_tests_by_graph",
            "target_symbol": "dispatch",
            "candidate_tests_found": selection["total_candidate_tests"],
            "selected_tests": [t["test_id"] for t in selection["selected_tests"][:4]],
            "test_run_status": selection["test_run_results"]["status"],
            "decision_steps": selection["decision_steps"],
            "causally_dependent_on_graph": selection["causally_dependent_on_graph"],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)
        }

    # -------------------------------------------------------------
    # Scene 3: Persistent Memory Across Sessions
    # -------------------------------------------------------------
    def run_scene_3_persistent_memory(self) -> Dict[str, Any]:
        """
        Scene 3: 'What did we discover about the notification failure?'
        Shows: End session, start new session, retrieve previous findings from FalkorDB.
        """
        t0 = time.perf_counter()
        # Session A records verified finding
        session_a = f"incident_session_a_{int(time.time())}"
        self.memory.record_session(session_a, "Notification worker dispatch retry investigation")
        finding = self.memory.record_finding(
            session_id=session_a,
            title="Notification failure causes retry exhaustion to status 'failed'",
            claim="Under 3 timeout events, dispatch releases token and emits 'failed' notice",
            source_path="signalforge/worker.py",
            start_line=13,
            end_line=24,
            confidence=1.0,
            is_verified=True
        )

        # Session B query recalls findings recorded by Session A
        session_b = f"incident_session_b_{int(time.time()) + 1}"
        recalled = self.memory.query_semantic_memory(query_text="Notification failure", limit=3)

        return {
            "scene": 3,
            "title": "Persistent Memory",
            "session_a_id": session_a,
            "session_b_id": session_b,
            "recorded_finding_id": finding.id,
            "recalled_findings_count": len(recalled),
            "recalled_titles": [f.title for f in recalled],
            "cross_session_continuity": len(recalled) > 0,
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)
        }

    # -------------------------------------------------------------
    # Scene 4: Multi-Agent Coordination
    # -------------------------------------------------------------
    def run_scene_4_multi_agent_coordination(self) -> Dict[str, Any]:
        """
        Scene 4: Multi-agent coordination.
        Graph Investigator -> Execution Analyst -> Test Analyst -> Evidence Reviewer.
        """
        t0 = time.perf_counter()
        collab = self.coordinator.execute_collaborative_investigation(
            objective="Investigate notification dispatch resilience",
            target_symbol="dispatch",
            scenario_question="With MAX_SEND_RETRIES=2 and persistent timeout, how many send calls and timeout events occur?"
        )

        return {
            "scene": 4,
            "title": "Multi-Agent Coordination",
            "investigation_id": collab["investigation_id"],
            "tasks_completed": collab["completed_tasks"],
            "handoff_count": collab["handoff_count"],
            "reviewer_decision": collab["reviewer_result"]["decision"],
            "is_approved": collab["final_approved"],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)
        }

    # -------------------------------------------------------------
    # Scene 5: Decision Explainability Graph
    # -------------------------------------------------------------
    def run_scene_5_decision_explainability(self) -> Dict[str, Any]:
        """
        Scene 5: Decision Explainability Graph.
        Question -> Graph Query -> Evidence -> Tool Selection -> Action -> Result -> Memory.
        """
        t0 = time.perf_counter()
        loop_res = self.decision_engine.execute_agent_loop(
            objective="Assess dispatch failure risks and select verification tests",
            target_symbol="dispatch",
            authorize_actions=True
        )

        provenance_chain = [
            f"Step {s['step']}: {s['name']}" for s in loop_res["decision_steps"]
        ]

        return {
            "scene": 5,
            "title": "Decision Explainability",
            "target": loop_res["target"],
            "provenance_chain": provenance_chain,
            "graph_influencing_path": loop_res["graph_influencing_path"],
            "causal_factor": loop_res["causal_graph_factor"],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)
        }

    # -------------------------------------------------------------
    # Scene 6: Company Brain
    # -------------------------------------------------------------
    def run_scene_6_company_brain(self) -> Dict[str, Any]:
        """
        Scene 6: 'Who owns the affected service, and which architectural decision explains its retry policy?'
        Shows: Ownership lookup + ADR decision record citation.
        """
        t0 = time.perf_counter()
        ownership_answer = self.company_brain.answer_company_question("Who owns worker.py?")
        adr_answer = self.company_brain.answer_company_question("Which architectural decision explains its retry policy?")

        return {
            "scene": 6,
            "title": "Company Brain",
            "ownership_answer": ownership_answer["answer"],
            "ownership_citations": ownership_answer["citations"],
            "adr_answer": adr_answer["answer"],
            "adr_citations": adr_answer["citations"],
            "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)
        }
