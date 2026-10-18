"""
app/ingestion/incremental.py - Ultra-Efficient Incremental Indexer & 3-Tier Execution Strategy.

Features:
- File SHA-256 content hashes to skip unchanged files
- Persistent hash storage (.asterion_hashes.json)
- Rename detection via content hash matching
- Graph write-back: delete_file, modify_file, rename_file
- Disconnected orphan node and edge pruning
- 3-Tier Execution Strategy:
  * Tier 1: Deterministic (0 LLM tokens, pure graph/AST queries)
  * Tier 2: Hybrid (Graph traversal + lightweight structural interpretation)
  * Tier 3: Deep Reasoning (Multi-phase scenario simulation, symbolic execution)
"""

import os
import ast
import json
import time
import hashlib
import logging
from typing import Dict, List, Set, Any, Optional

from app.graph.client import falkor_client
from app.graph.schema import NodeType, RelType

logger = logging.getLogger(__name__)


class IncrementalIndexer:
    """
    High-performance incremental code indexer for FalkorDB.
    Skips unchanged files using SHA-256 digests and performs targeted
    graph write-back for added, modified, renamed, and deleted files.
    """

    SUPPORTED_EXTENSIONS = (
        ".py", ".ts", ".tsx", ".js", ".jsx",
        ".java", ".c", ".cpp", ".sql",
        ".json", ".yaml", ".yml", ".md"
    )

    def __init__(self, repo_id: str, repo_path: str, hash_storage_path: Optional[str] = None):
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.graph_name = f"workspace_{repo_id}"
        self.hash_storage_path = hash_storage_path
        self._file_hashes: Dict[str, str] = {}
        self._last_index_time = 0.0
        if self.hash_storage_path:
            self.load_hashes()

    def compute_file_hash(self, file_path: str) -> str:
        full_path = file_path if os.path.isabs(file_path) else os.path.join(self.repo_path, file_path)
        try:
            with open(full_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def load_hashes(self, path: Optional[str] = None) -> Dict[str, str]:
        """Loads cached SHA-256 hashes from disk if available."""
        target_path = path or self.hash_storage_path
        if target_path and os.path.isfile(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self._file_hashes = data
            except Exception as e:
                logger.debug(f"Failed to load hashes from {target_path}: {e}")
        return self._file_hashes

    def save_hashes(self, path: Optional[str] = None) -> bool:
        """Persists current SHA-256 hashes to disk."""
        target_path = path or self.hash_storage_path
        if not target_path:
            return False
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(self._file_hashes, f, indent=2)
            return True
        except Exception as e:
            logger.debug(f"Failed to save hashes to {target_path}: {e}")
            return False

    def scan_repository(self) -> Dict[str, Any]:
        """
        Scans repository and identifies added, modified, unchanged, deleted,
        and renamed files using SHA-256 content hashes.
        """
        t0 = time.perf_counter()
        current_hashes: Dict[str, str] = {}
        for root, dirs, files in os.walk(self.repo_path):
            for ig in [".git", ".venv", "__pycache__", "node_modules", "dist", "build"]:
                if ig in dirs:
                    dirs.remove(ig)
            for f in files:
                if f == ".asterion_hashes.json" or any(sec in f for sec in [".env", ".pem", ".key", "secret", ".db", ".pyc"]):
                    continue
                if f.endswith(self.SUPPORTED_EXTENSIONS):
                    rel_p = os.path.relpath(os.path.join(root, f), self.repo_path)
                    current_hashes[rel_p] = self.compute_file_hash(rel_p)

        raw_added = [f for f in current_hashes if f not in self._file_hashes]
        modified = [f for f in current_hashes if f in self._file_hashes and current_hashes[f] != self._file_hashes[f]]
        unchanged = [f for f in current_hashes if f in self._file_hashes and current_hashes[f] == self._file_hashes[f]]
        raw_deleted = [f for f in self._file_hashes if f not in current_hashes]

        # Rename detection: identical content hash between raw_deleted and raw_added
        renamed = []
        deleted = []
        added = list(raw_added)
        added_by_hash = {current_hashes[a]: a for a in raw_added}

        for d in raw_deleted:
            old_h = self._file_hashes[d]
            if old_h and old_h in added_by_hash:
                new_f = added_by_hash[old_h]
                renamed.append({"old_path": d, "new_path": new_f})
                if new_f in added:
                    added.remove(new_f)
                del added_by_hash[old_h]
            else:
                deleted.append(d)

        dt = (time.perf_counter() - t0) * 1000.0
        return {
            "total_files_scanned": len(current_hashes),
            "added": added,
            "modified": modified,
            "unchanged": unchanged,
            "deleted": deleted,
            "renamed": renamed,
            "scan_time_ms": round(dt, 2),
            "current_hashes": current_hashes
        }

    def delete_file(self, file_path: str) -> bool:
        """
        Deletes File node and all symbols defined by this file, pruning connected edges.
        """
        norm_path = os.path.normpath(file_path).lstrip("/").lstrip("\\")
        try:
            falkor_client.connect()
            query = """
            MATCH (f:File {source_path: $path, repository_id: $repo_id})
            OPTIONAL MATCH (f)-[:DEFINES*1..2]->(s)
            DETACH DELETE s, f
            """
            falkor_client.safe_query(self.graph_name, query, {"path": norm_path, "repo_id": self.repo_id})

            sym_query = """
            MATCH (s)
            WHERE s.source_path = $path AND s.repository_id = $repo_id
            DETACH DELETE s
            """
            falkor_client.safe_query(self.graph_name, sym_query, {"path": norm_path, "repo_id": self.repo_id})

            if file_path in self._file_hashes:
                del self._file_hashes[file_path]
            if norm_path in self._file_hashes:
                del self._file_hashes[norm_path]
            return True
        except Exception as e:
            logger.error(f"Error deleting file {file_path} from graph: {e}")
            return False

    def rename_file(self, old_path: str, new_path: str) -> bool:
        """
        Renames a file in the graph, updating the File node and defined symbols' source_path.
        """
        norm_old = os.path.normpath(old_path).lstrip("/").lstrip("\\")
        norm_new = os.path.normpath(new_path).lstrip("/").lstrip("\\")
        new_name = os.path.basename(norm_new)
        try:
            falkor_client.connect()
            query = """
            MATCH (f:File {source_path: $old_path, repository_id: $repo_id})
            SET f.source_path = $new_path, f.name = $new_name
            """
            falkor_client.safe_query(self.graph_name, query, {
                "old_path": norm_old, "new_path": norm_new, "new_name": new_name, "repo_id": self.repo_id
            })

            sym_query = """
            MATCH (s)
            WHERE s.source_path = $old_path AND s.repository_id = $repo_id
            SET s.source_path = $new_path
            """
            falkor_client.safe_query(self.graph_name, sym_query, {
                "old_path": norm_old, "new_path": norm_new, "repo_id": self.repo_id
            })

            if norm_old in self._file_hashes:
                h = self._file_hashes.pop(norm_old)
                self._file_hashes[norm_new] = h
            return True
        except Exception as e:
            logger.error(f"Error renaming file {old_path} -> {new_path} in graph: {e}")
            return False

    def modify_file(self, file_path: str) -> Dict[str, Any]:
        """
        Deletes old symbols for this file and re-indexes the file into the graph.
        """
        norm_path = os.path.normpath(file_path).lstrip("/").lstrip("\\")
        try:
            falkor_client.connect()
            del_query = """
            MATCH (f:File {source_path: $path, repository_id: $repo_id})-[:DEFINES*1..2]->(s)
            DETACH DELETE s
            """
            falkor_client.safe_query(self.graph_name, del_query, {"path": norm_path, "repo_id": self.repo_id})

            sym_query = """
            MATCH (s)
            WHERE s.source_path = $path AND s.repository_id = $repo_id AND NOT (s:File)
            DETACH DELETE s
            """
            falkor_client.safe_query(self.graph_name, sym_query, {"path": norm_path, "repo_id": self.repo_id})

            from app.ingestion.pipeline import IngestionPipeline
            pipeline = IngestionPipeline(self.repo_path, self.repo_id)
            stats = pipeline.index_files([norm_path])

            self._file_hashes[norm_path] = self.compute_file_hash(norm_path)
            return stats
        except Exception as e:
            logger.error(f"Error modifying file {file_path}: {e}")
            return {"files_scanned": 0, "symbols_extracted": 0, "relationships_created": 0, "parsing_errors": 1}

    def prune_orphan_nodes(self) -> int:
        """
        Removes disconnected Concept or Module nodes that no longer have inbound or outbound edges.
        """
        try:
            falkor_client.connect()
            query = """
            MATCH (n)
            WHERE (n:Concept OR n:Module) AND n.repository_id = $repo_id AND NOT (n)--()
            DETACH DELETE n
            """
            falkor_client.safe_query(self.graph_name, query, {"repo_id": self.repo_id})
            return 1
        except Exception as e:
            logger.debug(f"Orphan pruning skipped/error: {e}")
            return 0

    def index_incrementally(self) -> Dict[str, Any]:
        """
        Performs fast incremental re-indexing, only parsing changed/added files,
        updating renamed files, deleting removed files, and pruning orphan nodes.
        """
        t0 = time.perf_counter()
        scan = self.scan_repository()

        renamed_count = 0
        for r in scan["renamed"]:
            if self.rename_file(r["old_path"], r["new_path"]):
                renamed_count += 1

        deleted_count = 0
        for d in scan["deleted"]:
            if self.delete_file(d):
                deleted_count += 1

        parsed_symbols_count = 0
        extracted_calls_count = 0
        files_processed = 0

        # Modified files: prune existing symbols and re-parse
        for m in scan["modified"]:
            stats = self.modify_file(m)
            parsed_symbols_count += stats.get("symbols_extracted", 0)
            extracted_calls_count += stats.get("relationships_created", 0)
            files_processed += 1

        # Added files: index into graph
        if scan["added"]:
            from app.ingestion.pipeline import IngestionPipeline
            pipeline = IngestionPipeline(self.repo_path, self.repo_id)
            stats = pipeline.index_files(scan["added"])
            parsed_symbols_count += stats.get("symbols_extracted", 0)
            extracted_calls_count += stats.get("relationships_created", 0)
            files_processed += len(scan["added"])

        if files_processed > 0 or deleted_count > 0:
            self.prune_orphan_nodes()

        # Update cached hashes and persist to disk
        self._file_hashes = scan["current_hashes"]
        self.save_hashes()
        self._last_index_time = time.time()
        dt = (time.perf_counter() - t0) * 1000.0

        return {
            "is_incremental": len(scan["unchanged"]) > 0,
            "files_processed": files_processed,
            "files_skipped_unchanged": len(scan["unchanged"]),
            "parsed_symbols": parsed_symbols_count,
            "extracted_calls": extracted_calls_count,
            "added_count": len(scan["added"]),
            "modified_count": len(scan["modified"]),
            "deleted_count": deleted_count,
            "renamed_count": renamed_count,
            "indexing_time_ms": round(dt, 2),
            "scan_time_ms": scan["scan_time_ms"]
        }


class ThreeTierExecutionRouter:
    """
    Directs queries to the most cost-efficient execution tier:
    - Tier 1: Deterministic (0 LLM tokens, pure graph/AST queries)
    - Tier 2: Hybrid (Graph traversal + lightweight structural interpretation)
    - Tier 3: Deep Reasoning (Multi-phase scenario simulation, symbolic execution)
    """

    @staticmethod
    def route_query_tier(question: str) -> Dict[str, Any]:
        q_lower = question.lower()

        # Tier 3: Deep reasoning (multi-phase, simulation, overrides, crash windows)
        if any(k in q_lower for k in [
            "simulate", "multiphase", "multi-phase", "replay", "reopened",
            "crash window", "exhausts retries", "change max_", "override to",
            "what breaks if", "mutation impact", "removal of"
        ]):
            return {
                "tier": 3,
                "tier_name": "DEEP_REASONING",
                "estimated_llm_cost": "MEDIUM_HIGH",
                "engine": "BoundedSymbolicExecutor & ControlFlowAnalyzer",
                "rationale": "Question requires state mutation simulation, failure loop replay, or impact evaluation."
            }

        # Tier 1: Deterministic (exact lookup, shortest path, call enumeration)
        if any(k in q_lower for k in [
            "shortest path", "enumerate static calls", "call path from",
            "who owns", "owner of", "which team", "adr-", "find symbol",
            "list callers", "inbound callers"
        ]):
            return {
                "tier": 1,
                "tier_name": "DETERMINISTIC",
                "estimated_llm_cost": "ZERO_TOKENS",
                "engine": "FalkorDB Direct Cypher & GraphAlgorithmEngine",
                "rationale": "Direct structural query resolvable without probabilistic LLM inference."
            }

        # Tier 2: Hybrid (default for general architectural queries)
        return {
            "tier": 2,
            "tier_name": "HYBRID",
            "estimated_llm_cost": "LOW",
            "engine": "Graph Traversal + Structural Synthesis",
            "rationale": "Combines graph evidence retrieval with concise structural explanation."
        }
