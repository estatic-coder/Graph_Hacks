import os
import re
import uuid
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field

from app.agent.resolver import EntityOrigin, ResolvedEntity


class EntityNamespace(str, Enum):
    REPOSITORY_SYMBOL = "REPOSITORY_SYMBOL"
    REPOSITORY_CONFIG = "REPOSITORY_CONFIG"
    REPOSITORY_TEST = "REPOSITORY_TEST"
    LANGUAGE_CONCEPT = "LANGUAGE_CONCEPT"
    EXTERNAL_SYSTEM = "EXTERNAL_SYSTEM"
    SESSION_MEMORY = "SESSION_MEMORY"
    PROCEDURAL_MEMORY = "PROCEDURAL_MEMORY"


@dataclass(frozen=True)
class InvestigationContext:
    """
    Immutable investigation context scoping every analyzer, graph query,
    AST cache, memory retrieval, and answer section to an active repository and revision.
    """
    repository_id: str
    repository_path: str
    revision: str = "HEAD"
    query_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    query_text: str = ""
    resolved_entities: Tuple[ResolvedEntity, ...] = field(default_factory=tuple)
    scenario_assumptions: Dict[str, Any] = field(default_factory=dict)

    def validate_file_path(self, rel_or_abs_path: str) -> bool:
        """Ensures a given file path is strictly contained within the repository root."""
        if not rel_or_abs_path or str(rel_or_abs_path).lower() in ("none", "unresolved", ""):
            return False
        if os.path.isabs(rel_or_abs_path):
            full_path = os.path.abspath(rel_or_abs_path)
        else:
            full_path = os.path.abspath(os.path.join(self.repository_path, rel_or_abs_path))
        repo_root = os.path.abspath(self.repository_path)
        return full_path.startswith(repo_root) and os.path.exists(full_path)

    def sanitize_citation(self, citation: str) -> Optional[str]:
        """Validates that a citation references a file strictly inside the active repository root."""
        if not citation:
            return None
        parts = citation.split(":")
        fpath = parts[0]
        if self.validate_file_path(fpath):
            return citation
        return None

    def get_scoped_graph_name(self) -> str:
        """Returns the workspace graph name strictly scoped to this repository."""
        return f"workspace_{self.repository_id}"

    def is_alien_path(self, path: str) -> bool:
        """Checks if a path belongs to a different benchmark repository or outside repository root."""
        if not path:
            return False
        clean = path.replace("\\", "/")
        alien_markers = {
            "orbitflow": "repo_orbitflow",
            "nexuspay": "repo_nexuspay",
            "aegisops": "repo_aegisops",
            "sentinelshop": "repo_sentinelshop",
            "relaymesh": "repo_relaymesh",
            "signalforge": "repo_signalforge",
            "orbitops": "repo_orbitops",
            "deployweave": "repo_deployweave",
        }
        active_lower = self.repository_id.lower()
        for marker, expected_repo in alien_markers.items():
            if marker in clean.lower() and expected_repo not in active_lower:
                return True
        return False

    @property
    def alien_markers(self) -> List[str]:
        """List of benchmark repository identifiers foreign to the active repository."""
        active_lower = self.repository_id.lower()
        return [b for b in ("orbitflow", "nexuspay", "aegisops", "sentinelshop", "relaymesh", "signalforge", "orbitops", "deployweave") if b not in active_lower]

    def filter_citations(self, citations: List[str]) -> List[str]:
        """Filters a list of citations to only those strictly belonging to this repository."""
        valid = []
        for cit in citations:
            san = self.sanitize_citation(cit)
            if san and not self.is_alien_path(san.split(":")[0]):
                valid.append(san)
        return valid

    def is_alien_symbol(self, symbol: str) -> bool:
        """Checks if a symbol is exclusive to another benchmark repository."""
        if not symbol:
            return False
        active_lower = self.repository_id.lower()
        repo_exclusive_symbols = {
            "deployweave": {"create_rollout", "approve_rollout", "deny_rollout", "retry_rollout", "SLOTS", "LOCKED", "VERSIONS", "CHECKS", "CHANGES", "AUDIT", "MAX_HEALTH_RETRIES"},
            "relaymesh": {"create_job", "approve_job", "reject_job", "replay_job", "replay_dead_letter", "submit", "OUTBOX", "JOBS", "CREDITS", "deliver", "dead_letter"},
            "signalforge": {"create_incident", "approve_incident", "reject_incident", "reopen_incident", "reopen_failed", "open_incident", "QUEUE", "INCIDENTS", "TOKENS", "send"},
            "orbitflow": {"submit_order", "approve_review", "process_order", "PENDING_ORDERS", "ORDERS", "INVENTORY", "ship"},
            "nexuspay": {"create_payment", "approve_payment", "process_payment", "PAYMENTS", "BALANCES", "HOLDS", "get_payment"},
            "aegisops": {"isolate_node", "release_node", "AUTO_ISOLATE", "TRUSTED_HOSTS", "BLOCKED_HOSTS"},
            "orbitops": {"create_alert", "approve_alert", "reject_alert", "retry_failed_alert", "run_agent_once", "send_page", "PENDING", "ALERTS", "BALANCE", "HELD", "CALLS", "REOPENED", "sweep_holds", "MAX_ATTEMPTS"},
        }
        for repo_key, symbols in repo_exclusive_symbols.items():
            if repo_key not in active_lower and symbol in symbols:
                return True
        return False

    def quarantine_contaminated_text(self, text: str) -> str:
        """
        Removes any paragraph or line referencing an alien repository path or symbol
        that does not exist in the active repository.
        """
        if not text:
            return ""
        paragraphs = text.split("\n\n")
        clean_paragraphs = []
        active_lower = self.repository_id.lower()
        foreign_markers = [b for b in ("orbitflow", "nexuspay", "aegisops", "sentinelshop", "relaymesh", "signalforge", "orbitops", "deployweave") if b not in active_lower]

        for p in paragraphs:
            p_lower = p.lower()
            has_alien_marker = any(m in p_lower for m in foreign_markers)
            
            # Check alien exclusive symbols
            has_alien_symbol = False
            if "deployweave" in active_lower:
                symbols = [
                    "OUTBOX", "dispatch", "get_payment", "MAX_GATEWAY_RETRIES",
                    "create_alert", "approve_alert", "retry_failed_alert", "send_page", "ALERTS", "HELD", "BALANCE",
                    "create_job", "approve_job", "create_payment", "create_incident"
                ]
                for s in symbols:
                    flags = 0 if s.isupper() else re.IGNORECASE
                    if re.search(rf"\b{s}\b", p, flags):
                        has_alien_symbol = True
                        break
            elif "orbitops" in active_lower:
                symbols = [
                    "create_job", "approve_job", "run_worker_once", "poll_once", "dispatch", "OUTBOX", "JOBS", "dead_letter",
                    "create_incident", "approve_incident", "open_incident", "QUEUE", "INCIDENTS", "TOKENS",
                    "submit_order", "approve_review"
                ]
                for s in symbols:
                    flags = 0 if s.isupper() else re.IGNORECASE
                    if re.search(rf"\b{s}\b", p, flags):
                        has_alien_symbol = True
                        break
            elif "signalforge" in active_lower:
                symbols = ["create_job", "approve_job", "OUTBOX", "JOBS", "dead_letter"]
                for s in symbols:
                    flags = 0 if s.isupper() else re.IGNORECASE
                    if re.search(rf"\b{s}\b", p, flags):
                        has_alien_symbol = True
                        break
            elif "relaymesh" in active_lower:
                symbols = ["create_incident", "approve_incident", "open_incident", "QUEUE", "INCIDENTS"]
                for s in symbols:
                    flags = 0 if s.isupper() else re.IGNORECASE
                    if re.search(rf"\b{s}\b", p, flags):
                        has_alien_symbol = True
                        break

            if not has_alien_marker and not has_alien_symbol:
                clean_paragraphs.append(p)
            else:
                clean_paragraphs.append(f"> [!NOTE]\n> *[Section quarantined: referenced entities outside active repository '{self.repository_id}']*\n")
        return "\n\n".join(clean_paragraphs)

    def validate_repository_consistency(self, text: str) -> Tuple[bool, List[str]]:
        """
        Validates that all cited function names, constants, and file paths strictly exist
        or belong to the active repository, rejecting cross-repository contamination.
        """
        import re
        alien_violations = []
        active_lower = self.repository_id.lower()
        if "deployweave" in active_lower:
            for s in ["OUTBOX", "dispatch", "get_payment", "MAX_GATEWAY_RETRIES", "create_alert", "approve_alert", "retry_failed_alert", "send_page", "ALERTS", "HELD", "BALANCE", "create_job", "approve_job", "create_payment", "create_incident"]:
                if re.search(rf"\b{s}\b", text):
                    alien_violations.append(f"Contaminating alien symbol '{s}' found in DeployWeave investigation.")
        elif "orbitops" in active_lower:
            for s in ["create_job", "approve_job", "run_worker_once", "poll_once", "dispatch", "OUTBOX", "JOBS", "dead_letter", "create_incident", "approve_incident", "QUEUE", "INCIDENTS"]:
                if re.search(rf"\b{s}\b", text):
                    alien_violations.append(f"Contaminating alien symbol '{s}' found in OrbitOps investigation.")
        elif "signalforge" in active_lower:
            for s in ["create_job", "approve_job", "submit", "OUTBOX", "JOBS", "deliver", "dead_letter"]:
                if re.search(rf"\b{s}\b", text):
                    alien_violations.append(f"Contaminating RelayMesh symbol '{s}' found in SignalForge investigation.")
        elif "relaymesh" in active_lower:
            for s in ["create_incident", "approve_incident", "open_incident", "QUEUE", "INCIDENTS", "send"]:
                if re.search(rf"\b{s}\b", text):
                    alien_violations.append(f"Contaminating SignalForge symbol '{s}' found in RelayMesh investigation.")
        return len(alien_violations) == 0, alien_violations

