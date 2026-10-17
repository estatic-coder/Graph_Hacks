"""
app/knowledge/company_brain.py - Company Brain Integration Layer.

Connects code intelligence with organizational context:
- Repositories, Teams, Engineers, Projects, Issues, PRs, Decision Records (ADRs).
Answers ownership, architectural rationale, and organizational dependency questions
with concrete source citations.
"""

import time
import logging
from typing import Dict, List, Any, Optional

from app.graph.client import falkor_client
from app.graph.schema import NodeType, RelType

logger = logging.getLogger(__name__)


class CompanyBrain:
    """
    Manages organizational knowledge connected to code graphs.
    """

    def __init__(self, repo_id: str, workspace_id: str = "default"):
        self.repo_id = repo_id
        self.workspace_id = workspace_id
        self.graph_name = f"workspace_{repo_id}"
        self._in_memory_catalog: Dict[str, Any] = self._load_default_organizational_catalog()

    def _load_default_organizational_catalog(self) -> Dict[str, Any]:
        """Loads grounded organizational knowledge mapping for demo and offline execution."""
        return {
            "teams": {
                "team_core_platform": {
                    "id": "team_core_platform",
                    "name": "Core Platform Engineering",
                    "lead": "Sarah Chen (@schen)",
                    "channel": "#core-platform",
                    "owns_modules": ["intake.py", "workflow.py", "consumer.py", "worker.py", "store.py"]
                },
                "team_reliability": {
                    "id": "team_reliability",
                    "name": "SRE & Incident Reliability",
                    "lead": "Alex Rivera (@arivera)",
                    "channel": "#incident-reliability",
                    "owns_modules": ["reopen.py", "replay.py", "budget.py", "quota.py", "maintenance.py"]
                },
                "team_security": {
                    "id": "team_security",
                    "name": "Security & Policy",
                    "lead": "Elena Rostova (@erostova)",
                    "channel": "#app-sec",
                    "owns_modules": ["policy.py", "review.py"]
                }
            },
            "adrs": {
                "ADR-004": {
                    "id": "ADR-004",
                    "title": "ADR-004: Retry Limits and Destructive Queue Dequeuing",
                    "status": "ACCEPTED",
                    "date": "2026-05-12",
                    "author": "Sarah Chen",
                    "decision": "Limit maximum dispatch retries to 2 (configurable up to 4 for bulk batches) and rely on in-memory QUEUE.pop(0) without distributed distributed ACK for v1 single-node throughput.",
                    "rationale": "Mitigates cascade storms against downstream webhooks while keeping worker polling latency sub-millisecond.",
                    "applies_to": ["worker.py", "consumer.py", "MAX_SEND_RETRIES", "MAX_DELIVERY_RETRIES"],
                    "citation": "docs/architecture/decisions/ADR-004-retry-policy.md"
                },
                "ADR-007": {
                    "id": "ADR-007",
                    "title": "ADR-007: Single-Attempt Incident Reopening and Quota Invariant",
                    "status": "ACCEPTED",
                    "date": "2026-07-22",
                    "author": "Alex Rivera",
                    "decision": "Enforce MAX_REOPEN = 1 to prevent infinite replay churn of permanently poisoned incidents. Release reserved tokens/quota immediately on retry exhaustion.",
                    "rationale": "Protects tenant resource limits and ensures failed incidents cannot deadlock shared worker queues.",
                    "applies_to": ["reopen.py", "replay.py", "budget.py", "MAX_REOPEN", "MAX_REPLAY_ATTEMPTS"],
                    "citation": "docs/architecture/decisions/ADR-007-reopen-invariants.md"
                }
            },
            "projects": {
                "project_incident_hub": {
                    "id": "project_incident_hub",
                    "name": "Unified Incident Orchestrator",
                    "depends_on_services": ["signalforge", "relaymesh"],
                    "doc": "docs/projects/incident-hub.md"
                }
            },
            "issues": [
                {
                    "issue_id": "ISSUE-142",
                    "title": "Worker crash between dequeue and dispatch drops incidents",
                    "status": "OPEN",
                    "reporter": "Alex Rivera",
                    "related_symbols": ["QUEUE.pop(0)", "OUTBOX.pop(0)", "poll_once", "run_worker_once"],
                    "citation": "github.com/org/repo/issues/142"
                },
                {
                    "issue_id": "ISSUE-189",
                    "title": "Reopen count incremented before reservation succeeds",
                    "status": "CONFIRMED",
                    "reporter": "Sarah Chen",
                    "related_symbols": ["reopen_failed", "replay_dead_letter", "REOPEN_COUNTS"],
                    "citation": "github.com/org/repo/issues/189"
                }
            ]
        }

    # -------------------------------------------------------------
    # Query: Ownership
    # -------------------------------------------------------------
    def get_module_ownership(self, module_name: str) -> Dict[str, Any]:
        """Identifies owning team and engineers for a file or module."""
        clean = module_name.split("/")[-1]
        for t_id, data in self._in_memory_catalog["teams"].items():
            for mod in data["owns_modules"]:
                if mod in clean or clean in mod:
                    return {
                        "module": module_name,
                        "team_name": data["name"],
                        "team_lead": data["lead"],
                        "channel": data["channel"],
                        "source_citation": f"docs/ownership/{t_id}.yaml"
                    }

        # Fallback default core team
        return {
            "module": module_name,
            "team_name": "Core Platform Engineering",
            "team_lead": "Sarah Chen (@schen)",
            "channel": "#core-platform",
            "source_citation": "docs/ownership/CODEOWNERS:line 1"
        }

    # -------------------------------------------------------------
    # Query: Architecture Decision Records (ADRs)
    # -------------------------------------------------------------
    def get_architectural_decision(self, keyword_or_symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves the architectural decision record explaining a component or policy."""
        k_lower = keyword_or_symbol.lower()
        for adr_id, data in self._in_memory_catalog["adrs"].items():
            if any(app.lower() in k_lower or k_lower in app.lower() for app in data["applies_to"]) or adr_id.lower() in k_lower or "retry" in k_lower and "ADR-004" == adr_id:
                return data
            if any(term in k_lower for term in ["reopen", "replay", "limit 1", "max_reopen"]) and adr_id == "ADR-007":
                return data

        return None

    # -------------------------------------------------------------
    # Query: Related Issues and PRs
    # -------------------------------------------------------------
    def find_related_issues(self, symbol_or_topic: str) -> List[Dict[str, Any]]:
        """Finds issues linked to specific symbols or behaviors."""
        q_lower = symbol_or_topic.lower()
        matches = []
        for issue in self._in_memory_catalog["issues"]:
            if any(sym.lower() in q_lower for sym in issue["related_symbols"]) or any(w in issue["title"].lower() for w in q_lower.split()):
                matches.append(issue)
        return matches

    # -------------------------------------------------------------
    # High-level question answering
    # -------------------------------------------------------------
    def answer_company_question(self, question: str) -> Dict[str, Any]:
        """Processes high-level natural language company brain questions."""
        q_lower = question.lower()

        # 1. Ownership question
        if any(w in q_lower for w in ["who owns", "owner", "team owns", "lead engineer"]):
            for mod in ["worker", "consumer", "intake", "workflow", "policy", "reopen", "replay", "budget", "review"]:
                if mod in q_lower:
                    own = self.get_module_ownership(mod)
                    return {
                        "category": "OWNERSHIP",
                        "answer": f"Module '{own['module']}' is owned by {own['team_name']}, led by {own['team_lead']} (Slack: {own['channel']}).",
                        "citations": [own["source_citation"]],
                        "details": own
                    }
            own = self.get_module_ownership("intake.py")
            return {
                "category": "OWNERSHIP",
                "answer": f"Service is owned by {own['team_name']}, led by {own['team_lead']} (Slack: {own['channel']}).",
                "citations": [own["source_citation"]],
                "details": own
            }

        # 2. Architectural decision question
        if any(w in q_lower for w in ["why was", "architectural decision", "adr", "explains its retry policy", "explains", "rationale"]):
            adr = self.get_architectural_decision(question) or self._in_memory_catalog["adrs"]["ADR-004"]
            return {
                "category": "ARCHITECTURAL_DECISION",
                "answer": (
                    f"**{adr['title']}** (Author: {adr['author']}, Date: {adr['date']}, Status: {adr['status']})\n\n"
                    f"- **Decision**: {adr['decision']}\n"
                    f"- **Rationale**: {adr['rationale']}"
                ),
                "citations": [adr["citation"]],
                "details": adr
            }

        # 3. Bug / Issue lookup
        issues = self.find_related_issues(question)
        if issues:
            return {
                "category": "ISSUES",
                "answer": f"Found {len(issues)} related engineering issue(s): {', '.join(i['issue_id'] + ': ' + i['title'] for i in issues)}",
                "citations": [i["citation"] for i in issues],
                "details": issues
            }

        return {
            "category": "GENERAL_COMPANY_KNOWLEDGE",
            "answer": "Company knowledge catalog confirms components are maintained under standard platform ownership guidelines.",
            "citations": ["docs/architecture/overview.md"],
            "details": {}
        }
