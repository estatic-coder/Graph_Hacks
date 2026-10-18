"""
app/services/retrieval.py - Hybrid Graph + Semantic Retrieval Engine (ASTERION V3)

Features:
- Code-aware tokenization (camelCase, snake_case, paths, signatures)
- BM25 lexical indexing with rank-bm25
- Graph neighborhood expansion (CALLS, IMPORTS, DEFINES, TESTS, DEPENDS_ON)
- Reciprocal Rank Fusion (RRF) & Weighted Multi-Modal Scoring
- Token budget context packaging for bounded LLM context injection
"""

import os
import re
import math
import time
import logging
from typing import Dict, List, Any, Optional, Tuple

from rank_bm25 import BM25Okapi

from app.graph.client import falkor_client
from app.graph.schema import NodeType

logger = logging.getLogger(__name__)


class CodeTokenizer:
    """Fast, code-aware tokenizer splitting identifiers, paths, and punctuation."""

    @staticmethod
    def tokenize(text: str) -> List[str]:
        if not text:
            return []
        
        # Replace non-alphanumeric punctuation with spaces except underscores and dots
        clean = re.sub(r'[^a-zA-Z0-9_\.]', ' ', text)
        raw_tokens = clean.split()
        tokens = []

        for token in raw_tokens:
            token_lower = token.lower()
            tokens.append(token_lower)

            # Split snake_case
            if "_" in token:
                parts = [p.lower() for p in token.split("_") if len(p) > 1]
                tokens.extend(parts)

            # Split dot paths
            if "." in token:
                parts = [p.lower() for p in token.split(".") if len(p) > 1]
                tokens.extend(parts)

            # Split CamelCase: parseTypeScript -> parse, type, script
            camel_parts = re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z][a-z]|\d|\W|$)|\d+', token)
            if len(camel_parts) > 1:
                tokens.extend([cp.lower() for cp in camel_parts if len(cp) > 1])

        # Deduplicate while preserving order and filter single char noise
        seen = set()
        result = []
        for t in tokens:
            if t not in seen and len(t) > 1:
                seen.add(t)
                result.append(t)

        return result


class HybridRetriever:
    """
    Hybrid code retrieval engine combining:
    1. Lexical BM25 ranking across symbol names, docstrings, paths, and signatures.
    2. Graph topological expansion (1-hop inbound/outbound relationships).
    3. Weighted fusion & Reciprocal Rank Fusion (RRF).
    4. Bounded token-budget context packaging for LLM prompting.
    """

    def __init__(self, repo_id: str, repo_path: Optional[str] = None):
        self.repo_id = repo_id
        self.repo_path = repo_path
        self.graph_name = f"workspace_{repo_id}"
        self.tokenizer = CodeTokenizer()
        self.items: List[Dict[str, Any]] = []
        self.bm25: Optional[BM25Okapi] = None
        self._is_indexed = False

    def build_index(self) -> int:
        """
        Builds the BM25 corpus from FalkorDB graph nodes and repository source files.
        """
        falkor_client.connect()
        self.items = []
        corpus_tokenized = []

        # 1. Fetch nodes from graph
        query = """
        MATCH (n)
        WHERE n.repository_id = $repo_id
        RETURN n.id, labels(n)[0], n.name, n.source_path, n.start_line, n.end_line
        """
        try:
            res = falkor_client.safe_query(self.graph_name, query, {"repo_id": self.repo_id})
            rows = getattr(res, "result_set", res) or []
            for r in rows:
                if isinstance(r, (list, tuple)) and len(r) >= 4:
                    nid = str(r[0])
                    ntype = str(r[1]) if len(r) > 1 and r[1] else "Symbol"
                    name = str(r[2]) if len(r) > 2 and r[2] else ""
                    source_path = str(r[3]) if len(r) > 3 and r[3] else ""
                    start_line = int(r[4]) if len(r) > 4 and r[4] is not None else 1
                    end_line = int(r[5]) if len(r) > 5 and r[5] is not None else 1
                elif hasattr(r[0], "properties"):
                    p = r[0].properties
                    nid = str(p.get("id", ""))
                    ntype = r[0].labels[0] if getattr(r[0], "labels", None) else "Symbol"
                    name = str(p.get("name", ""))
                    source_path = str(p.get("source_path", ""))
                    start_line = int(p.get("start_line", 1))
                    end_line = int(p.get("end_line", 1))
                else:
                    continue

                docstring = ""
                snippet = self._read_snippet(source_path, start_line, end_line)

                item = {
                    "id": nid,
                    "type": ntype,
                    "name": name,
                    "source_path": source_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "docstring": docstring,
                    "snippet": snippet
                }
                self.items.append(item)

                # Composite searchable document
                search_text = f"{name} {source_path} {ntype} {docstring} {snippet}"
                tokens = self.tokenizer.tokenize(search_text)
                corpus_tokenized.append(tokens if tokens else [name.lower()])
        except Exception as e:
            logger.debug(f"Error querying graph for retrieval index: {e}")

        # 2. Fallback: If graph returned empty but repo_path exists, scan repo files directly
        if not self.items and self.repo_path and os.path.isdir(self.repo_path):
            self._scan_filesystem_fallback(corpus_tokenized)

        if corpus_tokenized:
            self.bm25 = BM25Okapi(corpus_tokenized)
            self._is_indexed = True

        return len(self.items)

    def _read_snippet(self, source_path: str, start_line: int, end_line: int, max_lines: int = 40) -> str:
        """Reads code snippet from source file within line bounds."""
        if not self.repo_path or not source_path:
            return ""
        full_path = os.path.join(self.repo_path, source_path)
        if not os.path.isfile(full_path):
            return ""
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            st = max(0, start_line - 1)
            en = min(len(lines), max(st + 1, end_line))
            snippet_lines = lines[st:min(en, st + max_lines)]
            return "".join(snippet_lines).strip()
        except Exception:
            return ""

    def _scan_filesystem_fallback(self, corpus_tokenized: List[List[str]]) -> None:
        """Fallback to filesystem scanning when graph is not yet populated."""
        for root, dirs, files in os.walk(self.repo_path):
            for ig in [".git", ".venv", "__pycache__", "node_modules"]:
                if ig in dirs:
                    dirs.remove(ig)
            for f in files:
                if f.endswith((".py", ".ts", ".js", ".tsx", ".jsx", ".md")):
                    rel_p = os.path.relpath(os.path.join(root, f), self.repo_path)
                    snippet = self._read_snippet(rel_p, 1, 30)
                    item = {
                        "id": f"file_{self.repo_id}_{rel_p}",
                        "type": "File",
                        "name": f,
                        "source_path": rel_p,
                        "start_line": 1,
                        "end_line": 30,
                        "docstring": "",
                        "snippet": snippet
                    }
                    self.items.append(item)
                    tokens = self.tokenizer.tokenize(f"{f} {rel_p} {snippet}")
                    corpus_tokenized.append(tokens if tokens else [f.lower()])

    def retrieve(
        self,
        query: str,
        limit: int = 10,
        max_tokens: int = 4000,
        alpha: float = 0.6,
        expand_graph: bool = True
    ) -> Dict[str, Any]:
        """
        Executes hybrid retrieval:
        1. BM25 scoring over tokenized code corpus.
        2. Graph topological expansion (1-hop neighbors) & centrality scoring.
        3. Reciprocal Rank Fusion & weighted scoring.
        4. Strict token budget packaging for LLM injection.
        """
        t0 = time.perf_counter()

        if not self._is_indexed or not self.bm25 or not self.items:
            self.build_index()

        if not self.items or not self.bm25:
            return {
                "query": query,
                "total_candidates": 0,
                "returned_items": 0,
                "estimated_tokens": 0,
                "token_budget": max_tokens,
                "budget_used_pct": 0.0,
                "context_text": "No code symbols found in repository.",
                "items": [],
                "elapsed_ms": round((time.perf_counter() - t0) * 1000, 2)
            }

        # 1. Lexical BM25 Scoring
        q_tokens = self.tokenizer.tokenize(query)
        if not q_tokens:
            q_tokens = [query.lower()]

        bm25_raw = self.bm25.get_scores(q_tokens)
        max_bm25 = max(bm25_raw) if len(bm25_raw) > 0 and max(bm25_raw) > 0 else 1.0

        # Sort indices by BM25 score
        scored_indices = sorted(range(len(bm25_raw)), key=lambda i: bm25_raw[i], reverse=True)
        pool_size = min(len(self.items), max(limit * 3, 20))
        candidate_indices = scored_indices[:pool_size]

        # 2. Graph Topological Expansion & Centrality Scoring
        candidate_items = []
        for rank_bm25, idx in enumerate(candidate_indices):
            raw_item = dict(self.items[idx])
            norm_bm25 = float(bm25_raw[idx] / max_bm25) if max_bm25 > 0 else 0.0
            raw_item["bm25_score"] = round(norm_bm25, 4)
            raw_item["bm25_rank"] = rank_bm25 + 1

            # Fetch graph neighborhood
            neighbors = []
            graph_score = 0.0
            if expand_graph:
                try:
                    nbr_res = falkor_client.get_node_neighbors(self.graph_name, raw_item["id"], direction="both", limit=20)
                    for nbr in nbr_res:
                        if len(nbr) >= 3:
                            rel_type = str(nbr[0])
                            tgt_node = nbr[2]
                            tgt_props = getattr(tgt_node, "properties", {})
                            tgt_name = tgt_props.get("name", "")
                            tgt_type = tgt_node.labels[0] if getattr(tgt_node, "labels", None) else "Node"
                            neighbors.append({
                                "relation": rel_type,
                                "name": tgt_name,
                                "type": tgt_type
                            })
                    # Graph score proportional to degree centrality and relevance
                    graph_score = min(1.0, len(neighbors) / 10.0)
                except Exception as e:
                    logger.debug(f"Neighbor expansion error for {raw_item['id']}: {e}")

            raw_item["graph_score"] = round(graph_score, 4)
            raw_item["neighbors"] = neighbors
            candidate_items.append(raw_item)

        # 3. Hybrid Fusion & Reciprocal Rank Fusion (RRF)
        # Sort by graph score for graph rank
        sorted_by_graph = sorted(candidate_items, key=lambda x: x["graph_score"], reverse=True)
        for rank_g, it in enumerate(sorted_by_graph):
            it["graph_rank"] = rank_g + 1

        for it in candidate_items:
            # Weighted hybrid score: alpha * bm25 + (1 - alpha) * graph
            it["hybrid_score"] = round((alpha * it["bm25_score"]) + ((1.0 - alpha) * it["graph_score"]), 4)
            # RRF (k=60)
            it["rrf_score"] = round((1.0 / (60 + it["bm25_rank"])) + (1.0 / (60 + it["graph_rank"])), 5)

        # Final sort by hybrid score
        candidate_items.sort(key=lambda x: (x["hybrid_score"], x["rrf_score"]), reverse=True)

        # 4. Context Window Packager (Token Budget Enforcer)
        packaged_context_blocks = []
        packaged_items = []
        current_tokens = 0

        for it in candidate_items:
            block = self._format_item_markdown(it)
            est_tokens = math.ceil(len(block) / 3.8)

            if current_tokens + est_tokens > max_tokens and len(packaged_items) >= 1:
                # Truncate if token budget exhausted and at least 1 top match included
                break

            packaged_context_blocks.append(block)
            it["token_count"] = est_tokens
            packaged_items.append(it)
            current_tokens += est_tokens

            if len(packaged_items) >= limit:
                break

        full_context_text = "\n\n".join(packaged_context_blocks)
        dt = (time.perf_counter() - t0) * 1000.0

        return {
            "query": query,
            "total_candidates": len(candidate_items),
            "returned_items": len(packaged_items),
            "estimated_tokens": current_tokens,
            "token_budget": max_tokens,
            "budget_used_pct": round((current_tokens / max_tokens) * 100.0, 1) if max_tokens > 0 else 0.0,
            "context_text": full_context_text,
            "items": packaged_items,
            "elapsed_ms": round(dt, 2)
        }

    def _format_item_markdown(self, item: Dict[str, Any]) -> str:
        """Formats a retrieved code symbol into high-density Markdown for LLM prompt context."""
        lines = [
            f"### Symbol: `{item['name']}` ({item['type']})",
            f"- Path: `{item['source_path']}:{item['start_line']}-{item['end_line']}`",
            f"- Relevance: Hybrid={item['hybrid_score']:.3f} (BM25={item['bm25_score']:.3f}, Graph={item['graph_score']:.3f})"
        ]

        if item.get("neighbors"):
            nbr_summary = ", ".join([f"{n['relation']}->{n['name']}({n['type']})" for n in item["neighbors"][:6]])
            lines.append(f"- Neighborhood: {nbr_summary}")

        if item.get("docstring"):
            lines.append(f"- Docstring: {item['docstring']}")

        if item.get("snippet"):
            lines.append("```")
            lines.append(item["snippet"])
            lines.append("```")

        return "\n".join(lines)
