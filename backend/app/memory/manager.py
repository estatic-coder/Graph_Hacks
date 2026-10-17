import os
import hashlib
import logging
import subprocess
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from app.config import settings
from app.graph.client import falkor_client
from app.graph.schema import NodeType, RelType
from app.memory.models import (
    InvestigationSession,
    Finding,
    Hypothesis,
    InvestigationProcedure
)

logger = logging.getLogger(__name__)

class GraphMemoryManager:
    """
    Manages persistent episodic, semantic, and procedural graph memory in FalkorDB.
    Scopes memory by repository and workspace.
    Tracks source revisions and detects/invalidates stale findings.
    """

    def __init__(self, repo_id: str, repo_path: Optional[str] = None, workspace_id: str = "default"):
        self.repo_id = repo_id
        self.workspace_id = workspace_id
        self.graph_name = f"workspace_{repo_id}"
        if not repo_path:
            try:
                from app.repositories.manager import RepositoryManager
                meta = RepositoryManager().get_repository(repo_id)
                if meta and meta.source_path:
                    repo_path = meta.source_path
            except Exception:
                pass
        if not repo_path:
            if repo_id == "sample_1":
                repo_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../sample-repo"))
            else:
                raise ValueError(f"Repository '{repo_id}' not found.")
        self.repo_path = repo_path

    # ---------------------------------------------------------
    # Revision & Hash Helpers
    # ---------------------------------------------------------

    def get_current_revision(self) -> str:
        """
        Determines the current source code revision.
        Uses git commit hash if available, otherwise hashes directory file timestamps/sizes.
        """
        git_dir = os.path.join(self.repo_path, ".git")
        if os.path.exists(git_dir):
            try:
                top_level_res = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    cwd=self.repo_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
                top_level = (top_level_res.stdout or "").strip()
                if top_level and os.path.realpath(top_level) == os.path.realpath(self.repo_path):
                    res = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=self.repo_path,
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if res.returncode == 0 and res.stdout.strip():
                        return res.stdout.strip()
            except Exception:
                pass

        # Fallback deterministic revision hash based on files in repo
        hasher = hashlib.sha256()
        try:
            for root, _, files in sorted(os.walk(self.repo_path)):
                for f in sorted(files):
                    if f.endswith((".py", ".ts", ".tsx", ".js", ".json", ".md")):
                        p = os.path.join(root, f)
                        stat = os.stat(p)
                        hasher.update(f"{f}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"))
            return hasher.hexdigest()[:16]
        except Exception:
            return "rev_initial"

    def compute_snippet_hash(self, file_path: str, start_line: Optional[int], end_line: Optional[int]) -> str:
        """Computes a SHA-256 hash of the exact lines on disk to detect changes."""
        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.repo_path, file_path)
        if not os.path.exists(full_path) or not start_line or not end_line:
            return ""
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            s_idx = max(0, start_line - 1)
            e_idx = min(len(lines), end_line)
            snippet = "".join(lines[s_idx:e_idx])
            return hashlib.sha256(snippet.encode("utf-8")).hexdigest()
        except Exception as e:
            logger.warning(f"Error computing snippet hash for {file_path}: {e}")
            return ""

    # ---------------------------------------------------------
    # Episodic Memory (Investigation Sessions)
    # ---------------------------------------------------------

    def record_session(self, session_id: str, query: str, status: str = "completed") -> InvestigationSession:
        """Creates or updates an episodic InvestigationSession node in FalkorDB."""
        rev = self.get_current_revision()
        ts = datetime.now(timezone.utc).isoformat()
        node_id = f"sess_{self.repo_id}_{session_id}"

        cypher = """
        MERGE (s:InvestigationSession {id: $id})
        SET s.session_id = $session_id,
            s.repository_id = $repo_id,
            s.workspace_id = $workspace_id,
            s.query = $query,
            s.source_revision = $revision,
            s.timestamp = $timestamp,
            s.status = $status
        RETURN s.id
        """
        params = {
            "id": node_id,
            "session_id": session_id,
            "repo_id": self.repo_id,
            "workspace_id": self.workspace_id,
            "query": query,
            "revision": rev,
            "timestamp": ts,
            "status": status
        }
        try:
            falkor_client.safe_query(self.graph_name, cypher, params)
        except Exception as e:
            logger.error(f"Failed to record session in FalkorDB: {e}")

        return InvestigationSession(
            id=node_id,
            session_id=session_id,
            repo_id=self.repo_id,
            workspace_id=self.workspace_id,
            query=query,
            source_revision=rev,
            timestamp=ts,
            status=status
        )

    def get_session(self, session_id: str) -> Optional[InvestigationSession]:
        """Retrieves an investigation session by ID."""
        node_id = f"sess_{self.repo_id}_{session_id}"
        cypher = """
        MATCH (s:InvestigationSession {id: $id})
        RETURN s.id, s.session_id, s.repository_id, s.workspace_id, s.query, s.source_revision, s.timestamp, s.status
        """
        try:
            res = falkor_client.safe_query(self.graph_name, cypher, {"id": node_id})
            rows = getattr(res, "result_set", res) or []
            if rows:
                r = rows[0]
                return InvestigationSession(
                    id=str(r[0]),
                    session_id=str(r[1]),
                    repo_id=str(r[2]),
                    workspace_id=str(r[3]),
                    query=str(r[4]),
                    source_revision=str(r[5]),
                    timestamp=str(r[6]),
                    status=str(r[7])
                )
        except Exception as e:
            logger.error(f"Failed to get session {session_id}: {e}")
        return None

    def list_sessions(self, limit: int = 50) -> List[InvestigationSession]:
        """Lists past investigation sessions for this workspace and repo."""
        cypher = """
        MATCH (s:InvestigationSession)
        WHERE s.repository_id = $repo_id AND s.workspace_id = $workspace_id
        RETURN s.id, s.session_id, s.repository_id, s.workspace_id, s.query, s.source_revision, s.timestamp, s.status
        ORDER BY s.timestamp DESC
        LIMIT $limit
        """
        sessions = []
        try:
            res = falkor_client.safe_query(self.graph_name, cypher, {
                "repo_id": self.repo_id,
                "workspace_id": self.workspace_id,
                "limit": limit
            })
            rows = getattr(res, "result_set", res) or []
            for r in rows:
                sessions.append(InvestigationSession(
                    id=str(r[0]),
                    session_id=str(r[1]),
                    repo_id=str(r[2]),
                    workspace_id=str(r[3]),
                    query=str(r[4]),
                    source_revision=str(r[5]),
                    timestamp=str(r[6]),
                    status=str(r[7])
                ))
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
        return sessions

    # ---------------------------------------------------------
    # Semantic Memory (Verified Findings & Evidence)
    # ---------------------------------------------------------

    def record_finding(
        self,
        session_id: str,
        title: str,
        claim: str,
        source_path: Optional[str] = None,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None,
        graph_paths: Optional[List[str]] = None,
        referenced_symbol_ids: Optional[List[str]] = None,
        confidence: float = 1.0,
        is_verified: bool = True
    ) -> Finding:
        """
        Stores a verified finding into FalkorDB semantic memory.
        Connects finding to session (:RECORDED) and referenced entities (:REFERENCES).
        Rejects findings attempting to store procedural playbooks as repository evidence.
        """
        # Provenance safeguard: never store a procedural playbook as a verified repository finding
        if "workflow for " in title.lower() or "procedure" in title.lower():
            logger.warning(f"Memory write safeguard: Rejected procedural playbook as repository finding subject: '{title}'")
            return Finding(
                id="",
                finding_id="",
                session_id=session_id,
                repo_id=self.repo_id,
                workspace_id=self.workspace_id,
                title=title,
                claim=claim,
                source_revision="",
                source_path=source_path,
                start_line=start_line,
                end_line=end_line,
                snippet_hash="",
                is_verified=False
            )

        graph_paths = graph_paths or []
        referenced_symbol_ids = referenced_symbol_ids or []
        rev = self.get_current_revision()
        ts = datetime.now(timezone.utc).isoformat()
        
        # Deterministic unique finding ID
        seed = f"{self.repo_id}_{title}_{source_path}_{start_line}"
        finding_uid = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        node_id = f"finding_{self.repo_id}_{finding_uid}"
        snippet_hash = self.compute_snippet_hash(source_path, start_line, end_line) if source_path else ""

        cypher = """
        MERGE (f:Finding {id: $id})
        SET f.finding_id = $finding_id,
            f.session_id = $session_id,
            f.repository_id = $repo_id,
            f.workspace_id = $workspace_id,
            f.title = $title,
            f.claim = $claim,
            f.source_revision = $revision,
            f.source_path = $source_path,
            f.start_line = $start_line,
            f.end_line = $end_line,
            f.snippet_hash = $snippet_hash,
            f.is_verified = $is_verified,
            f.is_stale = false,
            f.stale_reason = null,
            f.confidence = $confidence,
            f.created_at = $created_at
        RETURN f.id
        """
        params = {
            "id": node_id,
            "finding_id": finding_uid,
            "session_id": session_id,
            "repo_id": self.repo_id,
            "workspace_id": self.workspace_id,
            "title": title,
            "claim": claim,
            "revision": rev,
            "source_path": source_path,
            "start_line": start_line,
            "end_line": end_line,
            "snippet_hash": snippet_hash,
            "is_verified": is_verified,
            "confidence": confidence,
            "created_at": ts
        }

        try:
            falkor_client.safe_query(self.graph_name, cypher, params)

            # Link Session -> Finding
            sess_node_id = f"sess_{self.repo_id}_{session_id}"
            link_sess_cypher = """
            MATCH (s:InvestigationSession {id: $sess_id})
            MATCH (f:Finding {id: $finding_id})
            MERGE (s)-[:RECORDED]->(f)
            """
            falkor_client.safe_query(self.graph_name, link_sess_cypher, {
                "sess_id": sess_node_id,
                "finding_id": node_id
            })

            # Link Finding -> Referenced Symbols (STRICT: Never link to Procedure or memory nodes)
            for sym_id in referenced_symbol_ids:
                link_sym_cypher = """
                MATCH (f:Finding {id: $finding_id})
                MATCH (sym {id: $sym_id})
                WHERE NOT sym:Procedure AND NOT sym:Finding AND NOT sym:InvestigationSession AND NOT sym:Hypothesis
                MERGE (f)-[:REFERENCES]->(sym)
                """
                falkor_client.safe_query(self.graph_name, link_sym_cypher, {
                    "finding_id": node_id,
                    "sym_id": sym_id
                })

            # Record source evidence node if snippet exists
            if source_path and start_line and end_line:
                ev_id = f"ev_{self.repo_id}_{finding_uid}"
                ev_cypher = """
                MERGE (e:SourceEvidence {id: $ev_id})
                SET e.file_path = $source_path,
                    e.start_line = $start_line,
                    e.end_line = $end_line,
                    e.snippet_hash = $snippet_hash,
                    e.repository_id = $repo_id
                WITH e
                MATCH (f:Finding {id: $finding_id})
                MERGE (f)-[:EVIDENCED_BY]->(e)
                """
                falkor_client.safe_query(self.graph_name, ev_cypher, {
                    "ev_id": ev_id,
                    "source_path": source_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "snippet_hash": snippet_hash,
                    "repo_id": self.repo_id,
                    "finding_id": node_id
                })

        except Exception as e:
            logger.error(f"Failed to record finding {title}: {e}")

        return Finding(
            id=node_id,
            finding_id=finding_uid,
            session_id=session_id,
            repo_id=self.repo_id,
            workspace_id=self.workspace_id,
            title=title,
            claim=claim,
            source_revision=rev,
            source_path=source_path,
            start_line=start_line,
            end_line=end_line,
            snippet_hash=snippet_hash,
            graph_paths=graph_paths,
            is_verified=is_verified,
            is_stale=False,
            confidence=confidence,
            referenced_symbol_ids=referenced_symbol_ids,
            created_at=ts
        )

    def query_semantic_memory(
        self,
        query_text: str = "",
        symbol_id: Optional[str] = None,
        include_stale: bool = False,
        limit: int = 10
    ) -> List[Finding]:
        """
        Searches semantic memory for verified findings.
        Can retrieve findings linked directly to a symbol or matching title/claim text.
        """
        findings = []
        try:
            if symbol_id:
                cypher = """
                MATCH (f:Finding)-[:REFERENCES]->(sym {id: $sym_id})
                WHERE f.repository_id = $repo_id AND f.workspace_id = $workspace_id
                  AND NOT sym:Procedure AND NOT sym:Finding AND NOT sym:InvestigationSession
                  AND (f.is_quarantined IS NULL OR f.is_quarantined = false)
                  AND NOT f.title CONTAINS 'Workflow for'
                """
                if not include_stale:
                    cypher += " AND (f.is_stale IS NULL OR f.is_stale = false)"
                cypher += """
                RETURN f.id, f.finding_id, f.session_id, f.repository_id, f.workspace_id,
                       f.title, f.claim, f.source_revision, f.source_path, f.start_line,
                       f.end_line, f.is_verified, f.is_stale, f.stale_reason, f.confidence, f.created_at
                ORDER BY f.created_at DESC LIMIT $limit
                """
                params = {
                    "sym_id": symbol_id,
                    "repo_id": self.repo_id,
                    "workspace_id": self.workspace_id,
                    "limit": limit
                }
            else:
                cypher = """
                MATCH (f:Finding)
                WHERE f.repository_id = $repo_id AND f.workspace_id = $workspace_id
                  AND (f.is_quarantined IS NULL OR f.is_quarantined = false)
                  AND NOT f.title CONTAINS 'Workflow for'
                """
                if not include_stale:
                    cypher += " AND (f.is_stale IS NULL OR f.is_stale = false)"
                cypher += """
                RETURN f.id, f.finding_id, f.session_id, f.repository_id, f.workspace_id,
                       f.title, f.claim, f.source_revision, f.source_path, f.start_line,
                       f.end_line, f.is_verified, f.is_stale, f.stale_reason, f.confidence, f.created_at
                ORDER BY f.created_at DESC LIMIT $limit
                """
                params = {
                    "repo_id": self.repo_id,
                    "workspace_id": self.workspace_id,
                    "limit": limit
                }

            res = falkor_client.safe_query(self.graph_name, cypher, params)
            rows = getattr(res, "result_set", res) or []
            for r in rows:
                finding = Finding(
                    id=str(r[0]),
                    finding_id=str(r[1]),
                    session_id=str(r[2]),
                    repo_id=str(r[3]),
                    workspace_id=str(r[4]),
                    title=str(r[5]),
                    claim=str(r[6]),
                    source_revision=str(r[7]),
                    source_path=str(r[8]) if r[8] else None,
                    start_line=int(r[9]) if r[9] is not None else None,
                    end_line=int(r[10]) if r[10] is not None else None,
                    is_verified=bool(r[11]),
                    is_stale=bool(r[12]),
                    stale_reason=str(r[13]) if r[13] else None,
                    confidence=float(r[14]) if r[14] is not None else 1.0,
                    created_at=str(r[15])
                )
                # If query_text is given and no specific symbol_id, filter by keyword / token overlap
                if query_text and not symbol_id:
                    q_lower = query_text.lower()
                    if q_lower in finding.title.lower() or q_lower in finding.claim.lower():
                        findings.append(finding)
                    else:
                        tokens = [w.strip("(),;:.!?\"'") for w in q_lower.split() if len(w.strip("(),;:.!?\"'")) >= 3]
                        if tokens and any(t in finding.title.lower() or t in finding.claim.lower() for t in tokens):
                            findings.append(finding)
                else:
                    findings.append(finding)
        except Exception as e:
            logger.error(f"Error querying semantic memory: {e}")
        return findings

    def recall_findings(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Recalls findings matching the given query as plain dictionaries."""
        findings = self.query_semantic_memory(query_text=query, limit=limit)
        return [{"id": f.id, "title": f.title, "claim": f.claim, "is_verified": f.is_verified} for f in findings]

    # ---------------------------------------------------------
    # Hypotheses (Unresolved Ideas / Hypotheses)
    # ---------------------------------------------------------

    def record_hypothesis(
        self,
        session_id: str,
        statement: str,
        target_symbol_ids: Optional[List[str]] = None
    ) -> Hypothesis:
        """Stores an unverified hypothesis or investigation hypothesis into memory."""
        target_symbol_ids = target_symbol_ids or []
        ts = datetime.now(timezone.utc).isoformat()
        seed = f"{self.repo_id}_{statement}"
        hypo_uid = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        node_id = f"hypo_{self.repo_id}_{hypo_uid}"

        cypher = """
        MERGE (h:Hypothesis {id: $id})
        SET h.hypo_id = $hypo_id,
            h.session_id = $session_id,
            h.repository_id = $repo_id,
            h.workspace_id = $workspace_id,
            h.statement = $statement,
            h.status = 'unresolved',
            h.resolution_notes = null,
            h.created_at = $created_at
        RETURN h.id
        """
        params = {
            "id": node_id,
            "hypo_id": hypo_uid,
            "session_id": session_id,
            "repo_id": self.repo_id,
            "workspace_id": self.workspace_id,
            "statement": statement,
            "created_at": ts
        }

        try:
            falkor_client.safe_query(self.graph_name, cypher, params)

            # Link Session -> Hypothesis
            sess_node_id = f"sess_{self.repo_id}_{session_id}"
            falkor_client.safe_query(self.graph_name, """
            MATCH (s:InvestigationSession {id: $sess_id})
            MATCH (h:Hypothesis {id: $hypo_id})
            MERGE (s)-[:PROPOSED]->(h)
            """, {"sess_id": sess_node_id, "hypo_id": node_id})

            # Link Hypothesis -> Target Symbols
            for sym_id in target_symbol_ids:
                falkor_client.safe_query(self.graph_name, """
                MATCH (h:Hypothesis {id: $hypo_id})
                MATCH (sym {id: $sym_id})
                MERGE (h)-[:TARGETS]->(sym)
                """, {"hypo_id": node_id, "sym_id": sym_id})

        except Exception as e:
            logger.error(f"Failed to record hypothesis: {e}")

        return Hypothesis(
            id=node_id,
            hypo_id=hypo_uid,
            session_id=session_id,
            repo_id=self.repo_id,
            workspace_id=self.workspace_id,
            statement=statement,
            status="unresolved",
            target_symbol_ids=target_symbol_ids,
            created_at=ts
        )

    def resolve_hypothesis(self, hypo_id: str, status: str, notes: str = ""):
        """Resolves an existing hypothesis (validated or rejected)."""
        node_id = hypo_id if hypo_id.startswith("hypo_") else f"hypo_{self.repo_id}_{hypo_id}"
        cypher = """
        MATCH (h:Hypothesis {id: $id})
        SET h.status = $status,
            h.resolution_notes = $notes
        RETURN h.id
        """
        try:
            falkor_client.safe_query(self.graph_name, cypher, {
                "id": node_id,
                "status": status,
                "notes": notes
            })
        except Exception as e:
            logger.error(f"Failed to resolve hypothesis {hypo_id}: {e}")

    def list_hypotheses(self, status: Optional[str] = "unresolved") -> List[Hypothesis]:
        """Lists hypotheses for this repo/workspace."""
        cypher = """
        MATCH (h:Hypothesis)
        WHERE h.repository_id = $repo_id AND h.workspace_id = $workspace_id
        """
        if status:
            cypher += " AND h.status = $status"
        cypher += """
        RETURN h.id, h.hypo_id, h.session_id, h.repository_id, h.workspace_id,
               h.statement, h.status, h.resolution_notes, h.created_at
        ORDER BY h.created_at DESC
        """
        hypotheses = []
        try:
            res = falkor_client.safe_query(self.graph_name, cypher, {
                "repo_id": self.repo_id,
                "workspace_id": self.workspace_id,
                "status": status
            })
            rows = getattr(res, "result_set", res) or []
            for r in rows:
                hypotheses.append(Hypothesis(
                    id=str(r[0]),
                    hypo_id=str(r[1]),
                    session_id=str(r[2]),
                    repo_id=str(r[3]),
                    workspace_id=str(r[4]),
                    statement=str(r[5]),
                    status=str(r[6]),
                    resolution_notes=str(r[7]) if r[7] else None,
                    created_at=str(r[8])
                ))
        except Exception as e:
            logger.error(f"Failed to list hypotheses: {e}")
        return hypotheses

    # ---------------------------------------------------------
    # Procedural Memory (Reusable Procedures)
    # ---------------------------------------------------------

    def record_procedure(
        self,
        name: str,
        intent_category: str,
        description: str,
        tool_sequence: List[str],
        query_template: str = ""
    ) -> InvestigationProcedure:
        """Stores a successful reusable investigation procedure into FalkorDB."""
        seed = f"{self.repo_id}_{name}_{intent_category}"
        proc_uid = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        node_id = f"proc_{self.repo_id}_{proc_uid}"

        cypher = """
        MERGE (p:Procedure {id: $id})
        SET p.proc_id = $proc_id,
            p.repository_id = $repo_id,
            p.name = $name,
            p.intent_category = $intent_category,
            p.description = $description,
            p.query_template = $query_template,
            p.success_count = coalesce(p.success_count, 0) + 1
        RETURN p.id
        """
        params = {
            "id": node_id,
            "proc_id": proc_uid,
            "repo_id": self.repo_id,
            "name": name,
            "intent_category": intent_category,
            "description": description,
            "query_template": query_template
        }
        try:
            falkor_client.safe_query(self.graph_name, cypher, params)
        except Exception as e:
            logger.error(f"Failed to record procedure {name}: {e}")

        return InvestigationProcedure(
            id=node_id,
            proc_id=proc_uid,
            repo_id=self.repo_id,
            name=name,
            intent_category=intent_category,
            description=description,
            tool_sequence=tool_sequence,
            query_template=query_template,
            success_count=1
        )

    def get_procedure(self, intent_category: str) -> Optional[InvestigationProcedure]:
        """Retrieves best matching procedure for given intent category."""
        cypher = """
        MATCH (p:Procedure)
        WHERE p.repository_id = $repo_id AND p.intent_category = $intent_category
        RETURN p.id, p.proc_id, p.repository_id, p.name, p.intent_category, p.description, p.query_template, p.success_count
        ORDER BY p.success_count DESC
        LIMIT 1
        """
        try:
            res = falkor_client.safe_query(self.graph_name, cypher, {
                "repo_id": self.repo_id,
                "intent_category": intent_category
            })
            rows = getattr(res, "result_set", res) or []
            if rows:
                r = rows[0]
                return InvestigationProcedure(
                    id=str(r[0]),
                    proc_id=str(r[1]),
                    repo_id=str(r[2]),
                    name=str(r[3]),
                    intent_category=str(r[4]),
                    description=str(r[5]),
                    query_template=str(r[6]) if r[6] else "",
                    success_count=int(r[7]) if r[7] is not None else 1
                )
        except Exception as e:
            logger.error(f"Failed to get procedure for {intent_category}: {e}")
        return None

    # ---------------------------------------------------------
    # Invalidation & Staleness Detection
    # ---------------------------------------------------------

    def invalidate_stale_findings(self, current_revision: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Inspects all active findings in FalkorDB and invalidates/flags stale findings
        after relevant code changes or file modifications.
        """
        current_rev = current_revision or self.get_current_revision()
        invalidated = []

        cypher = """
        MATCH (f:Finding)
        WHERE f.repository_id = $repo_id
          AND (f.is_stale IS NULL OR f.is_stale = false)
        RETURN f.id, f.title, f.source_revision, f.source_path, f.start_line, f.end_line, f.snippet_hash
        """
        try:
            res = falkor_client.safe_query(self.graph_name, cypher, {"repo_id": self.repo_id})
            rows = getattr(res, "result_set", res) or []
            for r in rows:
                f_id = str(r[0])
                title = str(r[1])
                f_rev = str(r[2]) if r[2] else ""
                src_path = str(r[3]) if r[3] else None
                s_line = int(r[4]) if r[4] is not None else None
                e_line = int(r[5]) if r[5] is not None else None
                old_hash = str(r[6]) if r[6] else ""

                stale_reason = None

                if src_path:
                    full_p = src_path if os.path.isabs(src_path) else os.path.join(self.repo_path, src_path)
                    if not os.path.exists(full_p):
                        stale_reason = f"Source file '{src_path}' was deleted from repository."
                    elif s_line and e_line and old_hash:
                        current_hash = self.compute_snippet_hash(src_path, s_line, e_line)
                        if current_hash and current_hash != old_hash:
                            stale_reason = f"Source code at '{src_path}:{s_line}-{e_line}' changed on disk."
                    elif f_rev and current_rev and f_rev != current_rev:
                        stale_reason = f"Repository revision advanced from '{f_rev[:8]}' to '{current_rev[:8]}'."

                if stale_reason:
                    set_cypher = """
                    MATCH (f:Finding {id: $id})
                    SET f.is_stale = true,
                        f.stale_reason = $reason
                    RETURN f.id
                    """
                    falkor_client.safe_query(self.graph_name, set_cypher, {
                        "id": f_id,
                        "reason": stale_reason
                    })
                    invalidated.append({
                        "finding_id": f_id,
                        "title": title,
                        "source_path": src_path,
                        "stale_reason": stale_reason
                    })
        except Exception as e:
            logger.error(f"Error checking stale findings: {e}")

        return invalidated

    def quarantine_contaminated_memories(self, dry_run: bool = False) -> Dict[str, Any]:
        """
        Identifies and isolates invalid memory records:
        - Findings referencing Procedure nodes or titled with procedural workflows.
        - Procedures improperly linked to SourceEvidence nodes.
        - Memories with mismatched or invalid provenance.
        Returns a dry-run report or execution summary without deleting genuine valid memory.
        """
        report: Dict[str, Any] = {
            "dry_run": dry_run,
            "contaminated_findings": [],
            "contaminated_procedure_links": [],
            "quarantined_items": [],
            "quarantined_count": 0
        }
        try:
            seen_ids = set()
            # 1a. Identify findings titled or claiming 'Workflow for...'
            find_title_cypher = """
            MATCH (f:Finding)
            WHERE f.repository_id = $repo_id
              AND (f.title CONTAINS 'Workflow for' OR f.claim CONTAINS 'Workflow for')
            RETURN f.id, f.title, f.source_path
            """
            res_t = falkor_client.safe_query(self.graph_name, find_title_cypher, {"repo_id": self.repo_id})
            rows_t = getattr(res_t, "result_set", res_t) or []
            for r in rows_t:
                fid = str(r[0])
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    item = {"id": fid, "title": str(r[1]), "source_path": str(r[2]) if r[2] else None}
                    report["contaminated_findings"].append(item)
                    report["quarantined_items"].append(item)

            # 1b. Identify findings referencing Procedure nodes
            find_ref_cypher = """
            MATCH (f:Finding)-[:REFERENCES]->(p:Procedure)
            WHERE f.repository_id = $repo_id
            RETURN f.id, f.title, f.source_path
            """
            res_r = falkor_client.safe_query(self.graph_name, find_ref_cypher, {"repo_id": self.repo_id})
            rows_r = getattr(res_r, "result_set", res_r) or []
            for r in rows_r:
                fid = str(r[0])
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    item = {"id": fid, "title": str(r[1]), "source_path": str(r[2]) if r[2] else None}
                    report["contaminated_findings"].append(item)
                    report["quarantined_items"].append(item)

            # 2. Identify procedure nodes linked to SourceEvidence
            proc_cypher = """
            MATCH (p:Procedure)-[r]->(e:SourceEvidence)
            WHERE p.repository_id = $repo_id
            RETURN p.id, p.name, e.id
            """
            res_p = falkor_client.safe_query(self.graph_name, proc_cypher, {"repo_id": self.repo_id})
            rows_p = getattr(res_p, "result_set", res_p) or []
            for rp in rows_p:
                p_item = {
                    "id": str(rp[0]),
                    "proc_id": str(rp[0]),
                    "title": str(rp[1]),
                    "proc_name": str(rp[1]),
                    "evidence_id": str(rp[2])
                }
                report["contaminated_procedure_links"].append(p_item)
                report["quarantined_items"].append(p_item)

            report["quarantined_count"] = len(report["quarantined_items"])

            if not dry_run and report["quarantined_count"] > 0:
                # Quarantine contaminated findings by title/claim
                quarantine_title_cypher = """
                MATCH (f:Finding)
                WHERE f.repository_id = $repo_id
                  AND (f.title CONTAINS 'Workflow for' OR f.claim CONTAINS 'Workflow for')
                SET f.is_quarantined = true,
                    f.is_stale = true,
                    f.stale_reason = 'Quarantined due to procedural-memory contamination'
                """
                falkor_client.safe_query(self.graph_name, quarantine_title_cypher, {"repo_id": self.repo_id})

                # Quarantine findings referencing procedures and sever the reference edge
                quarantine_ref_cypher = """
                MATCH (f:Finding)-[r:REFERENCES]->(p:Procedure)
                WHERE f.repository_id = $repo_id
                SET f.is_quarantined = true,
                    f.is_stale = true,
                    f.stale_reason = 'Quarantined due to procedural-memory contamination'
                DELETE r
                """
                falkor_client.safe_query(self.graph_name, quarantine_ref_cypher, {"repo_id": self.repo_id})

                # Delete any invalid links between Procedure and SourceEvidence
                del_proc_links = """
                MATCH (p:Procedure)-[r]->(e:SourceEvidence)
                WHERE p.repository_id = $repo_id
                DELETE r
                """
                falkor_client.safe_query(self.graph_name, del_proc_links, {"repo_id": self.repo_id})
                logger.info(f"Quarantined {report['quarantined_count']} contaminated memory associations for repo {self.repo_id}")

        except Exception as e:
            logger.error(f"Error during memory quarantine: {e}")
            report["error"] = str(e)

        return report
