"""
app/agents/code_navigator.py - CodeNavigatorAgent for symbol resolution and path discovery.
"""

import time
from typing import Dict, Any, Optional, List
from app.agents.base_agent import BaseAgent
from app.agents.approval import RiskLevel
from app.graph.client import falkor_client
from app.services.retrieval import HybridRetriever

class CodeNavigatorAgent(BaseAgent):
    """
    Specialized agent for navigating repository topology, locating symbols,
    and tracing cross-module import paths.
    """

    def __init__(self, repo_id: str, repo_path: Optional[str] = None, approval_gate=None):
        super().__init__(
            role="CodeNavigator",
            repo_id=repo_id,
            repo_path=repo_path,
            approval_gate=approval_gate
        )
        self.retriever = HybridRetriever(repo_id=repo_id, repo_path=repo_path)

    def locate_symbol(self, symbol_name: str) -> List[Dict[str, Any]]:
        """Finds symbols matching name directly in FalkorDB graph or via hybrid retrieval."""
        query = """
        MATCH (s)
        WHERE s.repository_id = $repo_id AND s.name = $name
        RETURN s.id, labels(s)[0], s.name, s.source_path, s.start_line, s.end_line
        """
        try:
            res = falkor_client.safe_query(self.graph_name, query, {"repo_id": self.repo_id, "name": symbol_name})
            rows = getattr(res, "result_set", res) or []
            matches = []
            for r in rows:
                if len(r) >= 6:
                    matches.append({
                        "id": str(r[0]),
                        "type": str(r[1]),
                        "name": str(r[2]),
                        "source_path": str(r[3]),
                        "start_line": int(r[4]) if r[4] is not None else 1,
                        "end_line": int(r[5]) if r[5] is not None else 1
                    })
            if matches:
                return matches
        except Exception:
            pass

        # Fallback to hybrid retrieval
        ret = self.retriever.retrieve(symbol_name, limit=3, expand_graph=False)
        return ret.get("items", [])

    def resolve_dependencies(self, symbol_id: str) -> List[Dict[str, Any]]:
        """Finds outbound dependencies (CALLS, IMPORTS, DEPENDS_ON) for the symbol."""
        nbrs = falkor_client.get_node_neighbors(self.graph_name, symbol_id, direction="out", limit=25)
        deps = []
        for n in nbrs:
            if len(n) >= 3:
                rel = str(n[0])
                node = n[2]
                props = getattr(node, "properties", {})
                deps.append({
                    "relation": rel,
                    "target_id": props.get("id"),
                    "target_name": props.get("name"),
                    "target_type": node.labels[0] if getattr(node, "labels", None) else "Symbol"
                })
        return deps

    def execute_step(self, task: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        task_id = f"nav_{int(time.time())}"
        self.record_task(task_id, description=task)

        target = (context or {}).get("target_symbol") or task.split()[-1]
        matches = self.locate_symbol(target)

        action = self.record_action(
            task_id=task_id,
            action_type="LOCATE_SYMBOL",
            details={"target": target, "matches_count": len(matches)},
            risk_level=RiskLevel.LOW
        )

        return {
            "agent_role": self.role,
            "target": target,
            "matches": matches,
            "action": action,
            "status": "COMPLETED"
        }
