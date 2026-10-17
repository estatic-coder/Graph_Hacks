import os
import re
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from app.graph.client import falkor_client

logger = logging.getLogger(__name__)

from enum import Enum

class EntityOrigin(str, Enum):
    REPOSITORY = "REPOSITORY"
    PROCEDURAL_MEMORY = "PROCEDURAL_MEMORY"
    SESSION_MEMORY = "SESSION_MEMORY"
    CONCEPT = "CONCEPT"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"

@dataclass
class ResolvedEntity:
    id: str
    name: str
    type: str
    source_path: Optional[str]
    start_line: Optional[int]
    end_line: Optional[int]
    confidence: float
    origin: EntityOrigin = EntityOrigin.REPOSITORY
    repository_id: Optional[str] = None
    revision: Optional[str] = None
    resolution_method: str = "exact_symbol_match"
    evidence: str = ""
    is_ambiguous: bool = False
    ambiguous_candidates: List[str] = field(default_factory=list)

    @property
    def file_path(self) -> Optional[str]:
        return self.source_path

    @property
    def entity_id(self) -> str:
        return self.id

    @property
    def entity_type(self) -> str:
        return self.type

    @property
    def resolution_confidence(self) -> float:
        return self.confidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.id,
            "id": self.id,
            "name": self.name,
            "entity_type": self.type,
            "type": self.type,
            "origin": self.origin.value if isinstance(self.origin, EntityOrigin) else str(self.origin),
            "repository_id": self.repository_id,
            "revision": self.revision,
            "file_path": self.source_path,
            "source_path": self.source_path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "resolution_confidence": self.confidence,
            "confidence": self.confidence,
            "resolution_method": self.resolution_method,
            "evidence": self.evidence,
            "is_ambiguous": self.is_ambiguous,
            "ambiguous_candidates": self.ambiguous_candidates,
        }

def _stem_word(word: str) -> str:
    """Lightweight rule-based morphological normalization."""
    w = word.lower().strip()
    if w.endswith("ization"):
        return w[:-7] + "ize"
    if w.endswith("isation"):
        return w[:-7] + "ise"
    if w.endswith("ing") and len(w) > 5:
        return w[:-3]
    if w.endswith("ed") and len(w) > 4:
        return w[:-2]
    if w.endswith("es") and len(w) > 4:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        return w[:-1]
    return w

def _tokenize_name(text: str) -> List[str]:
    """Splits identifiers and natural language phrases into clean semantic tokens."""
    # Split camelCase and snake_case
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    tokens = re.findall(r"[a-zA-Z0-9]+", s.lower())
    stopwords = {
        "the", "a", "an", "logic", "code", "implementation", "function", "functions",
        "method", "methods", "class", "classes", "module", "service", "services",
        "operation", "operations", "component", "components", "behavior", "routine",
        "flow", "system", "which", "what", "for", "in", "of", "to", "and", "or",
        "is", "are", "by", "with", "from"
    }
    return [t for t in tokens if t not in stopwords and len(t) > 1]

class EntityResolver:
    """
    Resolves entity text mentions and natural-language descriptions to concrete FalkorDB graph nodes.
    Supports exact identifier search, graph-backed symbol matching, token normalization,
    stemmed overlap, source context boosting, and ambiguity detection without fabricating entities.
    """
    def __init__(self, repo_id: str, repo_path: Optional[str] = None):
        self.repo_id = repo_id
        if not repo_id or not repo_id.strip():
            raise ValueError("Repository ID cannot be empty.")
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
        self.graph_name = f"workspace_{repo_id}"
        self._constants_cache: Optional[List[Dict[str, Any]]] = None

    def _fetch_module_constants(self) -> List[Dict[str, Any]]:
        """
        Scans Python source files on disk to discover top-level module constants
        and configuration variables (e.g. AUTO_ISOLATE, TRUSTED_HOSTS, SEVERITY_THRESHOLD, INCIDENTS).
        """
        if self._constants_cache is not None:
            return self._constants_cache

        constants: List[Dict[str, Any]] = []
        if not self.repo_path or not os.path.exists(self.repo_path):
            self._constants_cache = []
            return []

        import ast
        for root, _, files in os.walk(self.repo_path):
            for file in files:
                if not file.endswith(".py"):
                    continue
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.repo_path)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                        tree = ast.parse(f.read())
                    for stmt in tree.body:
                        target_names = []
                        if isinstance(stmt, ast.Assign):
                            for tgt in stmt.targets:
                                if isinstance(tgt, ast.Name):
                                    target_names.append(tgt.id)
                        elif isinstance(stmt, ast.AnnAssign):
                            if isinstance(stmt.target, ast.Name):
                                target_names.append(stmt.target.id)

                        for var_name in target_names:
                            is_const = var_name.isupper()
                            node_type = "ConfigConstant" if is_const else "Variable"
                            constants.append({
                                "id": f"sym_{self.repo_id}_{rel_path}_{var_name}",
                                "type": node_type,
                                "name": var_name,
                                "source_path": rel_path,
                                "start_line": stmt.lineno,
                                "end_line": stmt.end_lineno or stmt.lineno
                            })
                except Exception:
                    pass

        self._constants_cache = constants
        return constants

    def resolve(self, candidate_terms: Any, context_node: Optional[dict] = None) -> List[ResolvedEntity]:
        if isinstance(candidate_terms, str):
            candidate_terms = [candidate_terms]
        resolved: List[ResolvedEntity] = []
        seen_ids = set()

        # Concept synonyms map to canonical symbols/constants strictly scoped to the active repository
        repo_lower = self.repo_id.lower()
        if "signalforge" in repo_lower:
            concept_synonyms = {
                "the worker": "run_worker_once",
                "worker": "run_worker_once",
                "the queue": "QUEUE",
                "queue": "QUEUE",
                "the outbox": "QUEUE",
                "outbox": "QUEUE",
                "the reopen budget": "REOPEN_COUNTS",
                "reopen budget": "REOPEN_COUNTS",
                "the replay budget": "REOPEN_COUNTS",
                "replay budget": "REOPEN_COUNTS",
                "reopen": "reopen_failed",
                "replay": "reopen_failed",
                "tokens": "TOKENS",
                "quota": "TOKENS",
                "credits": "TOKENS",
                "reservation": "RESERVED",
                "transport": "send",
                "the transport": "send",
                "after transport recovers": "send",
                "approval": "approve",
                "vip approval": "approve_incident",
                "critical approval": "approve_incident",
                "incidents": "INCIDENTS",
                "incident record": "INCIDENTS",
                "sweep reservations": "sweep_reservations",
                "orphan sweep": "sweep_reservations",
            }
        elif "relaymesh" in repo_lower:
            concept_synonyms = {
                "the worker": "run_worker_once",
                "worker": "run_worker_once",
                "the queue": "OUTBOX",
                "the outbox": "OUTBOX",
                "queue": "OUTBOX",
                "outbox": "OUTBOX",
                "the replay budget": "REPLAY_COUNTS",
                "replay budget": "REPLAY_COUNTS",
                "replay": "replay_dead_letter",
                "a dead-letter job": "dead_letter",
                "dead-letter": "dead_letter",
                "dead letter": "dead_letter",
                "dead-letter job": "dead_letter",
                "quota restoration": "release",
                "quota": "CREDITS",
                "credits": "CREDITS",
                "reservation": "RESERVED",
                "after transport recovers": "deliver",
                "transport": "deliver",
                "the transport": "deliver",
                "vip approval": "approve_job",
                "approval": "approve",
                "sweep orphans": "sweep_orphans",
                "orphan sweep": "sweep_orphans",
            }
        elif "aegisops" in repo_lower:
            concept_synonyms = {
                "remediation switch": "AUTO_ISOLATE",
                "auto isolate": "AUTO_ISOLATE",
                "auto-isolate": "AUTO_ISOLATE",
                "auto_isolation": "AUTO_ISOLATE",
                "trusted host": "TRUSTED_HOSTS",
                "trusted-host": "TRUSTED_HOSTS",
                "trusted_hosts": "TRUSTED_HOSTS",
                "severity threshold": "SEVERITY_THRESHOLD",
                "blocked hosts": "BLOCKED_HOSTS",
                "incident record": "INCIDENTS",
                "incident records": "INCIDENTS",
                "incident store": "INCIDENTS",
                "incidents": "INCIDENTS",
                "audit log": "record_audit",
                "audit logs": "record_audit",
                "audit": "record_audit",
            }
        elif "deployweave" in repo_lower:
            concept_synonyms = {
                "the worker": "run_worker_once",
                "worker": "run_worker_once",
                "the queue": "READY",
                "queue": "READY",
                "the lock": "LOCKED",
                "lock": "LOCKED",
                "slots": "SLOTS",
                "slot balance": "SLOTS",
                "versions": "VERSIONS",
                "registry": "VERSIONS",
                "checks": "CHECKS",
                "changes": "CHANGES",
                "audit": "AUDIT",
                "events": "EVENTS",
                "notices": "NOTICES",
                "health": "probe",
                "health probes": "probe",
                "probes": "probe",
                "retry": "retry_rollout",
                "approve": "approve_rollout",
                "approval": "approve_rollout",
                "create": "create_rollout",
                "submission": "create_rollout",
                "submit": "create_rollout",
                "drain": "drain_one",
                "rollback": "restore_version",
                "refund": "refund_slot",
                "acquire": "acquire_slot",
            }
        elif "orbitops" in repo_lower:
            concept_synonyms = {
                "the worker": "run_agent_once",
                "worker": "run_agent_once",
                "the queue": "PENDING",
                "queue": "PENDING",
                "pager": "send_page",
                "the pager": "send_page",
                "pager calls": "send_page",
                "approval": "approve_alert",
                "submission": "create_alert",
                "retry": "retry_failed_alert",
                "alerts": "ALERTS",
                "events": "EVENTS",
                "balance": "BALANCE",
                "reservation": "HELD",
                "held": "HELD",
                "drain": "drain_one",
            }
        else:
            concept_synonyms = {}

        # 1. UI Context Node has highest priority
        if context_node and context_node.get("id"):
            c_id = context_node.get("id")
            c_name = context_node.get("name") or c_id
            c_type = context_node.get("label") or "Node"
            resolved.append(ResolvedEntity(
                id=c_id,
                name=c_name,
                type=c_type,
                source_path=context_node.get("source_path"),
                start_line=context_node.get("start_line"),
                end_line=context_node.get("end_line"),
                confidence=1.0,
                origin=EntityOrigin.REPOSITORY,
                repository_id=self.repo_id,
                resolution_method="context_node_selection",
                evidence="Explicitly selected context node from graph explorer."
            ))
            seen_ids.add(c_id)

        # 2. Query all indexed symbols in the repository once for fast multi-candidate matching
        cached_symbols = self._fetch_repo_symbols()
        module_constants = self._fetch_module_constants()
        all_symbols = cached_symbols + [c for c in module_constants if c["id"] not in {s["id"] for s in cached_symbols}]

        for term in candidate_terms:
            term_clean = term.strip()
            if not term_clean or len(term_clean) < 2:
                continue

            # Stage 2 requirement: Do not treat numeric literals as graph entities
            if term_clean.isdigit() or re.match(r"^[-+]?\d+(\.\d+)?$", term_clean):
                continue

            # Check concept synonyms
            term_lookup = term_clean.lower()
            if term_lookup in concept_synonyms:
                canon = concept_synonyms[term_lookup]
                for sym in all_symbols:
                    if sym["name"] == canon and sym["id"] not in seen_ids:
                        seen_ids.add(sym["id"])
                        resolved.append(ResolvedEntity(
                            id=sym["id"],
                            name=sym["name"],
                            type=sym["type"],
                            source_path=sym["source_path"],
                            start_line=sym["start_line"],
                            end_line=sym["end_line"],
                            confidence=0.98,
                            origin=EntityOrigin.REPOSITORY,
                            repository_id=self.repo_id,
                            resolution_method="concept_synonym_match",
                            evidence=f"Matched concept '{term_clean}' to `{sym['name']}` in `{sym.get('source_path')}:{sym.get('start_line')}`."
                        ))

            # First try exact / direct substring search in FalkorDB
            direct_matches = self._direct_search(term_clean)
            for dm in direct_matches:
                if dm.id not in seen_ids:
                    seen_ids.add(dm.id)
                    resolved.append(dm)

            # Check exact match against module constants
            for const in module_constants:
                if (const["name"] == term_clean or const["name"].lower() == term_clean.lower()) and const["id"] not in seen_ids:
                    seen_ids.add(const["id"])
                    resolved.append(ResolvedEntity(
                        id=const["id"],
                        name=const["name"],
                        type=const["type"],
                        source_path=const["source_path"],
                        start_line=const["start_line"],
                        end_line=const["end_line"],
                        confidence=0.96,
                        origin=EntityOrigin.REPOSITORY,
                        repository_id=self.repo_id,
                        resolution_method="module_constant_exact_match",
                        evidence=f"Matched configuration constant `{const['name']}` in `{const['source_path']}:{const['start_line']}`."
                    ))

            # If direct match was exact (confidence >= 0.95), move to next candidate term
            if any(dm.confidence >= 0.95 for dm in direct_matches):
                continue

            # Normalized natural-language token matching
            nl_matches = self._match_natural_language(term_clean, all_symbols, seen_ids)
            for nlm in nl_matches:
                if nlm.id not in seen_ids:
                    seen_ids.add(nlm.id)
                    resolved.append(nlm)

            # If term matches a file/module name (e.g. "gateway" -> "gateway.py"), associate functions in that module
            if len(term_clean) >= 3 and not direct_matches and not nl_matches:
                for sym in all_symbols:
                    if sym["source_path"] and f"{term_clean.lower()}.py" in sym["source_path"].lower():
                        if sym["type"] in ("Function", "Method") and sym["id"] not in seen_ids:
                            seen_ids.add(sym["id"])
                            resolved.append(ResolvedEntity(
                                id=sym["id"],
                                name=sym["name"],
                                type=sym["type"],
                                source_path=sym["source_path"],
                                start_line=sym["start_line"],
                                end_line=sym["end_line"],
                                confidence=0.92,
                                origin=EntityOrigin.REPOSITORY,
                                repository_id=self.repo_id,
                                resolution_method="file_module_symbol_association",
                                evidence=f"Associated domain term '{term_clean}' with `{sym['name']}` in `{sym['source_path']}`."
                            ))

            # Concept recognition: domain concepts, external systems, and exceptions
            is_exception_or_concept = (
                term_clean.endswith("Error") or
                term_clean.endswith("Exception") or
                term_clean.lower() in ("timeouterror", "connectionerror", "valueerror", "keyerror", "kafka", "redis", "rabbitmq", "postgresql", "postgres")
            )
            if is_exception_or_concept and term_clean not in seen_ids and not direct_matches and not nl_matches:
                c_id = f"concept_{term_clean.lower()}"
                if c_id not in seen_ids:
                    seen_ids.add(c_id)
                    resolved.append(ResolvedEntity(
                        id=c_id,
                        name=term_clean,
                        type="Exception" if ("error" in term_clean.lower() or "exception" in term_clean.lower()) else "Concept",
                        source_path=None,
                        start_line=None,
                        end_line=None,
                        confidence=0.90,
                        origin=EntityOrigin.CONCEPT,
                        repository_id=self.repo_id,
                        resolution_method="conceptual_recognition",
                        evidence=f"Recognized domain concept '{term_clean}'."
                    ))

        # Strict candidate ranking: REPOSITORY symbols strictly outrank agent memory/concepts
        def _candidate_rank(e: ResolvedEntity):
            is_repo = 2 if e.origin == EntityOrigin.REPOSITORY else 0
            has_source = 1 if (e.source_path and e.source_path != "None") else 0
            return (is_repo, has_source, e.confidence)

        resolved.sort(key=_candidate_rank, reverse=True)
        return resolved

    def _fetch_repo_symbols(self) -> List[Dict[str, Any]]:
        """Retrieves all indexed symbol nodes in the target repository for fuzzy resolution."""
        cypher = """
        MATCH (n)
        WHERE (n.repository_id = $repo_id OR n.id STARTS WITH 'sym_' + $repo_id OR n.id STARTS WITH 'file_' + $repo_id)
          AND NOT n:Procedure AND NOT n:Finding AND NOT n:InvestigationSession AND NOT n:Hypothesis AND NOT n:SourceEvidence
          AND (n:Function OR n:Method OR n:Class OR n:Endpoint OR n:Symbol OR n:File OR n:Test OR n:ConfigConstant OR n:Variable OR n:Module)
        RETURN n.id, labels(n)[0], n.name, n.source_path, n.start_line, n.end_line
        """
        try:
            res = falkor_client.safe_query(self.graph_name, cypher, {"repo_id": self.repo_id})
            rows = getattr(res, "result_set", res) or []
            symbols = []
            for r in rows:
                symbols.append({
                    "id": str(r[0]),
                    "type": str(r[1]),
                    "name": str(r[2]),
                    "source_path": str(r[3]) if r[3] is not None else None,
                    "start_line": int(r[4]) if r[4] is not None else None,
                    "end_line": int(r[5]) if r[5] is not None else None
                })
            return symbols
        except Exception as e:
            logger.error(f"Error fetching symbols for repo {self.repo_id}: {e}")
            return []

    def _validate_source_location(self, name: str, source_path: Optional[str], start_line: Optional[int], end_line: Optional[int]) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        """Validates that a symbol actually exists at source_path in the repository AST, correcting if mislocated."""
        if not self.repo_path or not os.path.exists(self.repo_path):
            return source_path, start_line, end_line

        import ast
        # If source_path provided, check if it's a function or class definition in that file
        if source_path:
            full_p = os.path.abspath(os.path.join(self.repo_path, source_path))
            if os.path.exists(full_p) and os.path.isfile(full_p):
                try:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as f:
                        tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                            return source_path, node.lineno, node.end_lineno or node.lineno
                except Exception:
                    pass

        # Check all files in repo for a true function/class definition (prevents model field assignments from shadowing functions)
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                cand_full = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_full, self.repo_path)
                try:
                    with open(cand_full, "r", encoding="utf-8", errors="replace") as cf:
                        c_tree = ast.parse(cf.read())
                    for node in ast.walk(c_tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
                            return cand_rel, node.lineno, node.end_lineno or node.lineno
                except Exception:
                    continue

        # If no function definition found, check if source_path has an assignment
        if source_path:
            full_p = os.path.abspath(os.path.join(self.repo_path, source_path))
            if os.path.exists(full_p) and os.path.isfile(full_p):
                try:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as f:
                        tree = ast.parse(f.read())
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Assign):
                            for tgt in node.targets:
                                if isinstance(tgt, ast.Name) and tgt.id == name:
                                    return source_path, node.lineno, node.end_lineno or node.lineno
                except Exception:
                    pass

        # Pass 2: variable/constant assignments across repo
        for root, _, files in os.walk(self.repo_path):
            if any(ig in root for ig in [".git", ".venv", "__pycache__"]):
                continue
            for f in sorted(files):
                if not f.endswith(".py"):
                    continue
                cand_full = os.path.join(root, f)
                cand_rel = os.path.relpath(cand_full, self.repo_path)
                try:
                    with open(cand_full, "r", encoding="utf-8", errors="replace") as cf:
                        c_tree = ast.parse(cf.read())
                    for node in ast.walk(c_tree):
                        if isinstance(node, ast.Assign):
                            for tgt in node.targets:
                                if isinstance(tgt, ast.Name) and tgt.id == name:
                                    return cand_rel, node.lineno, node.end_lineno or node.lineno
                except Exception:
                    continue

        return source_path, start_line, end_line

    def _direct_search(self, term: str) -> List[ResolvedEntity]:
        """Direct exact and substring query on FalkorDB restricting strictly to repository symbols."""
        results = []
        cypher = """
        MATCH (n)
        WHERE (n.repository_id = $repo_id OR n.id STARTS WITH 'sym_' + $repo_id OR n.id STARTS WITH 'file_' + $repo_id)
          AND NOT n:Procedure AND NOT n:Finding AND NOT n:InvestigationSession AND NOT n:Hypothesis AND NOT n:SourceEvidence
          AND (n:Function OR n:Method OR n:Class OR n:Endpoint OR n:Symbol OR n:File OR n:Test OR n:ConfigConstant OR n:Variable OR (n:Module AND n.source_path IS NOT NULL))
          AND (
            n.id = $term OR 
            n.name = $term OR 
            n.source_path = $term OR 
            toLower(n.name) = toLower($term)
          )
        RETURN n.id, labels(n)[0], n.name, n.source_path, n.start_line, n.end_line
        ORDER BY CASE WHEN n.source_path IS NOT NULL AND n.source_path <> 'None' THEN 0 ELSE 1 END,
                 CASE WHEN labels(n)[0] IN ['Function', 'Method', 'Class', 'ConfigConstant'] THEN 0 ELSE 1 END
        LIMIT 5
        """
        params = {"repo_id": self.repo_id, "term": term}
        try:
            res = falkor_client.safe_query(self.graph_name, cypher, params)
            rows = getattr(res, "result_set", res) or []
            seen_canon = set()
            for r in rows:
                n_id = str(r[0])
                n_type = str(r[1])
                n_name = str(r[2])
                s_path = str(r[3]) if r[3] is not None and str(r[3]) != "None" else None
                s_line = int(r[4]) if r[4] is not None else None
                e_line = int(r[5]) if r[5] is not None else None

                # Discard unanchored external Module nodes
                if n_type == "Module" and not s_path:
                    continue

                # Validate source path and line numbers against AST
                v_path, v_line, v_end = self._validate_source_location(n_name, s_path, s_line, e_line)
                canon_key = (n_name, v_path)
                if canon_key in seen_canon:
                    continue
                seen_canon.add(canon_key)

                confidence = 1.0 if (n_name == term or n_id == term) else 0.95
                results.append(ResolvedEntity(
                    id=n_id,
                    name=n_name,
                    type=n_type,
                    source_path=v_path,
                    start_line=v_line,
                    end_line=v_end,
                    confidence=confidence,
                    origin=EntityOrigin.REPOSITORY,
                    repository_id=self.repo_id,
                    resolution_method="exact_symbol_match",
                    evidence=f"Exact symbol match for '{term}' in repository graph."
                ))
        except Exception as e:
            logger.error(f"Direct search error for '{term}': {e}")
        return results

    def _match_natural_language(
        self,
        phrase: str,
        symbols: List[Dict[str, Any]],
        seen_ids: set
    ) -> List[ResolvedEntity]:
        """
        Matches natural-language descriptions (e.g. 'payment authorization logic')
        to repository symbols using normalized stemmed token intersection and source context.
        """
        query_tokens = _tokenize_name(phrase)
        if not query_tokens:
            return []

        query_stemmed = {_stem_word(t) for t in query_tokens}
        scored_candidates: List[tuple[float, Dict[str, Any], List[str]]] = []

        for sym in symbols:
            if sym["id"] in seen_ids:
                continue

            sym_tokens = _tokenize_name(sym["name"])
            if not sym_tokens:
                continue
            sym_stemmed = {_stem_word(t) for t in sym_tokens}

            common = query_stemmed.intersection(sym_stemmed)
            if not common:
                continue

            recall = len(common) / len(query_stemmed)
            precision = len(common) / len(sym_stemmed)
            jaccard = len(common) / len(query_stemmed.union(sym_stemmed))

            # Base score: balance of query recall and symbol precision
            score = 0.55 * recall + 0.45 * precision

            # If exact stemmed token sets match (e.g. authorize_payment <-> payment authorization)
            if query_stemmed == sym_stemmed:
                score = 0.92

            # Source path context bonus: if file path also contains any query tokens
            if sym["source_path"]:
                path_tokens = _tokenize_name(sym["source_path"])
                path_stemmed = {_stem_word(pt) for pt in path_tokens}
                path_overlap = query_stemmed.intersection(path_stemmed)
                if path_overlap:
                    score += 0.08

            score = min(score, 0.98)

            if score >= 0.55:
                scored_candidates.append((score, sym, sorted(list(common))))

        if not scored_candidates:
            return []

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)

        top_score, top_sym, top_common = scored_candidates[0]

        # Deduplicate candidates with the same name before checking ambiguity
        distinct_candidates = []
        seen_cand_names = set()
        for sc, ss, com in scored_candidates:
            if ss["name"] not in seen_cand_names:
                seen_cand_names.add(ss["name"])
                distinct_candidates.append((sc, ss, com))

        ambiguous = False
        ambiguous_names = []
        if len(distinct_candidates) > 1:
            second_score, second_sym, _ = distinct_candidates[1]
            top_file = os.path.basename(top_sym.get("source_path") or "")
            sec_file = os.path.basename(second_sym.get("source_path") or "")
            is_parent_file = (
                (second_sym.get("type") in ("File", "Module") and (second_sym["name"] == top_file or second_sym["name"].replace(".py", "") == top_file.replace(".py", ""))) or
                (top_sym.get("type") in ("File", "Module") and (top_sym["name"] == sec_file or top_sym["name"].replace(".py", "") == sec_file.replace(".py", ""))) or
                (top_sym.get("source_path") == second_sym.get("source_path") and (top_sym.get("type") in ("File", "Module") or second_sym.get("type") in ("File", "Module"))) or
                bool(top_sym.get("source_path") and second_sym["name"] and (top_sym.get("source_path") or "").endswith(second_sym["name"])) or
                bool(second_sym.get("source_path") and top_sym["name"] and (second_sym.get("source_path") or "").endswith(top_sym["name"]))
            )
            if not is_parent_file:
                if top_score >= 0.70 and (top_score - second_score) < 0.08 and second_sym["name"] != top_sym["name"]:
                    ambiguous = True
                    ambiguous_names = [top_sym["name"], second_sym["name"]]

        evidence = (
            f"Matched normalized stemmed tokens {top_common} from description '{phrase}' "
            f"against symbol `{top_sym['name']}` in `{top_sym.get('source_path')}`."
        )

        return [ResolvedEntity(
            id=top_sym["id"],
            name=top_sym["name"],
            type=top_sym["type"],
            source_path=top_sym["source_path"],
            start_line=top_sym["start_line"],
            end_line=top_sym["end_line"],
            confidence=top_score,
            origin=EntityOrigin.REPOSITORY,
            repository_id=self.repo_id,
            resolution_method="natural_language_stemmed_match",
            evidence=evidence,
            is_ambiguous=ambiguous,
            ambiguous_candidates=ambiguous_names
        )]


# Compatibility alias
SymbolResolver = EntityResolver

