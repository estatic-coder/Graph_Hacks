"""
app/agent/graph_algorithms.py - Deterministic Graph Reasoning Algorithms.

Implements deterministic graph algorithms for code intelligence:
- Tarjan's Strongly Connected Components (SCC) algorithm for cycle detection
- Directed BFS for unweighted shortest paths with ordered hops and proof of non-reachability
- In-degree and out-degree calculations for function and service ranking
- Dependency traversal separating imports from calls in upstream and downstream directions
- Reverse-reachability change-impact analysis with deduplication and supporting paths
"""

import os
import ast
import logging
from typing import Dict, List, Set, Tuple, Any, Optional
from collections import defaultdict, deque

from app.graph.client import falkor_client

logger = logging.getLogger(__name__)


def _ensure_graph_indexed(repo_id: str, repo_path: str) -> str:
    """Ensures the repository is indexed in FalkorDB (live or mock)."""
    graph_name = f"workspace_{repo_id}"
    
    # Check if graph exists in mock client or if safe_query returns nodes
    has_nodes = False
    if hasattr(falkor_client, "graphs") and graph_name in falkor_client.graphs:
        if len(falkor_client.graphs[graph_name].get("nodes", {})) > 0:
            has_nodes = True
            
    if not has_nodes and falkor_client.check_health():
        try:
            res = falkor_client.safe_query(graph_name, "MATCH (n) RETURN count(n)")
            if res and hasattr(res, "result_set") and res.result_set:
                cnt = res.result_set[0][0] if len(res.result_set[0]) > 0 else 0
                if cnt > 0:
                    has_nodes = True
        except Exception:
            pass

    if not has_nodes and repo_path and os.path.isdir(repo_path):
        try:
            from app.ingestion.pipeline import IngestionPipeline
            pipe = IngestionPipeline(repo_path=repo_path, repo_id=repo_id)
            pipe.index()
        except Exception as e:
            logger.warning(f"Failed to auto-index repo {repo_id}: {e}")

    return graph_name


def _extract_graph_adjacency(
    repo_id: str,
    repo_path: str,
    relations: Tuple[str, ...] = ("CALLS", "IMPORTS", "DEPENDS_ON")
) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, List[Tuple[str, str]]], Dict[str, List[Tuple[str, str]]]]:
    """
    Extracts nodes and adjacency lists from FalkorDB (or in-memory mock).
    Returns (nodes_dict, forward_adj, reverse_adj).
    forward_adj: src_id -> list of (target_id, relation_type)
    reverse_adj: target_id -> list of (src_id, relation_type)
    """
    graph_name = _ensure_graph_indexed(repo_id, repo_path)
    nodes: Dict[str, Dict[str, Any]] = {}
    forward_adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    reverse_adj: Dict[str, List[Tuple[str, str]]] = defaultdict(list)

    # 1. Try in-memory mock client directly if available
    if hasattr(falkor_client, "graphs") and graph_name in falkor_client.graphs:
        g = falkor_client.graphs[graph_name]
        for nid, n in g.get("nodes", {}).items():
            nodes[nid] = {
                "id": nid,
                "name": str(n.properties.get("name") or nid),
                "labels": list(n.labels),
                "source_path": str(n.properties.get("source_path") or ""),
                "start_line": int(n.properties.get("start_line") or 1),
                "end_line": int(n.properties.get("end_line") or 1),
                "properties": dict(n.properties)
            }
        for edge in g.get("edges", []):
            if edge.relation in relations:
                forward_adj[edge.source].append((edge.target, edge.relation))
                reverse_adj[edge.target].append((edge.source, edge.relation))
        return nodes, forward_adj, reverse_adj

    # 2. Live FalkorDB Cypher queries
    try:
        # Fetch nodes
        n_res = falkor_client.safe_query(
            graph_name,
            "MATCH (n) RETURN n.id, labels(n)[0], coalesce(n.name, n.id), n.source_path, n.start_line, n.end_line"
        )
        if n_res and hasattr(n_res, "result_set"):
            for row in n_res.result_set:
                nid = str(row[0])
                nodes[nid] = {
                    "id": nid,
                    "labels": [str(row[1]) if row[1] else "Node"],
                    "name": str(row[2]) if row[2] else nid,
                    "source_path": str(row[3]) if row[3] else "",
                    "start_line": int(row[4]) if row[4] else 1,
                    "end_line": int(row[5]) if row[5] else 1,
                    "properties": {}
                }

        # Fetch edges
        e_res = falkor_client.safe_query(
            graph_name,
            "MATCH (n)-[r]->(m) RETURN n.id, type(r), m.id"
        )
        if e_res and hasattr(e_res, "result_set"):
            for row in e_res.result_set:
                src, rel, tgt = str(row[0]), str(row[1]), str(row[2])
                if rel in relations:
                    forward_adj[src].append((tgt, rel))
                    reverse_adj[tgt].append((src, rel))

    except Exception as e:
        logger.error(f"Error querying graph adjacency for {repo_id}: {e}")

    return nodes, forward_adj, reverse_adj


# =============================================================================
# 1. Strongly Connected Components (Tarjan's Algorithm)
# =============================================================================

def compute_strongly_connected_components(
    repo_id: str,
    repo_path: str,
    granularity: str = "service"
) -> Dict[str, Any]:
    """
    Computes Strongly Connected Components using Tarjan's linear-time DFS algorithm.
    By default operates on the service-to-service dependency graph (imports + calls).
    """
    nodes, forward_adj, _ = _extract_graph_adjacency(
        repo_id, repo_path, relations=("CALLS", "IMPORTS", "DEPENDS_ON")
    )

    if granularity == "service":
        service_edges: Dict[str, Set[str]] = defaultdict(set)
        all_services: Set[str] = set()

        for nid, ndata in nodes.items():
            sp = ndata.get("source_path", "")
            if "services/" in sp:
                parts = sp.split("services/")[1].split("/")
                if parts and parts[0]:
                    all_services.add(parts[0])

        for src, tgts in forward_adj.items():
            src_node = nodes.get(src, {})
            src_sp = src_node.get("source_path", "")
            if "services/" in src_sp:
                src_svc = src_sp.split("services/")[1].split("/")[0]
                for tgt, _ in tgts:
                    tgt_node = nodes.get(tgt, {})
                    tgt_sp = tgt_node.get("source_path", "")
                    if "services/" in tgt_sp:
                        tgt_svc = tgt_sp.split("services/")[1].split("/")[0]
                        if src_svc and tgt_svc and src_svc != tgt_svc:
                            service_edges[src_svc].add(tgt_svc)

        # Execute Tarjan's algorithm
        index = 0
        indices: Dict[str, int] = {}
        lowlinks: Dict[str, int] = {}
        on_stack: Set[str] = set()
        stack: List[str] = []
        sccs: List[List[str]] = []

        def strongconnect(v: str):
            nonlocal index
            indices[v] = index
            lowlinks[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)

            for w in sorted(service_edges.get(v, set())):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(sorted(scc))

        for s in sorted(all_services):
            if s not in indices:
                strongconnect(s)

        # Classify components
        non_trivial = [c for c in sccs if len(c) > 1]
        trivial = [c for c in sccs if len(c) == 1]

        return {
            "algorithm": "Tarjan's strongly connected components",
            "granularity": "service",
            "total_services": len(all_services),
            "total_components": len(sccs),
            "non_trivial_cycles_count": len(non_trivial),
            "non_trivial_components": non_trivial,
            "trivial_components_count": len(trivial),
            "trivial_components": [c[0] for c in trivial],
            "all_components": sccs,
            "service_dependency_edges": {k: sorted(list(v)) for k, v in service_edges.items()}
        }

    return {"error": f"Granularity {granularity} not supported"}


# =============================================================================
# 2. Directed BFS for Unweighted Shortest Path
# =============================================================================

def compute_directed_shortest_path(
    repo_id: str,
    repo_path: str,
    source_service: str = "gateway",
    target_service: str = "audit"
) -> Dict[str, Any]:
    """
    Finds the shortest directed call path from source_service to target_service using BFS.
    Returns ordered sequence of nodes, edges, hop citations, and service-level hops.
    """
    nodes, forward_adj, _ = _extract_graph_adjacency(repo_id, repo_path, relations=("CALLS",))

    # Identify source functions and target functions
    src_funcs = [
        nid for nid, n in nodes.items()
        if f"services/{source_service}/" in n.get("source_path", "") and ("Function" in n.get("labels", []) or "Method" in n.get("labels", []))
    ]
    tgt_funcs = set(
        nid for nid, n in nodes.items()
        if f"services/{target_service}/" in n.get("source_path", "") and ("Function" in n.get("labels", []) or "Method" in n.get("labels", []))
    )

    # Breadth-first search for shortest path
    queue = deque([(sf, [sf]) for sf in sorted(src_funcs)])
    visited = set(src_funcs)
    found_path: Optional[List[str]] = None

    while queue:
        curr, path = queue.popleft()
        if curr in tgt_funcs:
            found_path = path
            break
        for nxt, rel in forward_adj.get(curr, []):
            if nxt not in visited:
                visited.add(nxt)
                queue.append((nxt, path + [nxt]))

    if found_path:
        hops = []
        ordered_services = []
        citations = []
        for idx in range(len(found_path)):
            nid = found_path[idx]
            ndata = nodes.get(nid, {})
            sp = ndata.get("source_path", "")
            s_name = ndata.get("name", nid)
            s_line = ndata.get("start_line", 1)
            svc = sp.split("services/")[1].split("/")[0] if "services/" in sp else "unknown"
            if not ordered_services or ordered_services[-1] != svc:
                ordered_services.append(svc)
            citations.append(f"{sp}:{s_line}")
            hops.append({
                "hop_index": idx,
                "node_id": nid,
                "symbol_name": s_name,
                "source_path": sp,
                "line": s_line,
                "service": svc
            })

        return {
            "path_found": True,
            "source_service": source_service,
            "target_service": target_service,
            "total_hops": len(found_path) - 1,
            "total_nodes": len(found_path),
            "ordered_hops": hops,
            "ordered_services": ordered_services,
            "citations": citations
        }
    else:
        # Mathematical proof of non-reachability
        tgt_inbound_count = sum(len([s for s, _ in forward_adj.items() if any(t == tf for t, _ in forward_adj[s])]) for tf in tgt_funcs)
        return {
            "path_found": False,
            "source_service": source_service,
            "target_service": target_service,
            "proof": f"Directed BFS completed across all {len(visited)} reachable nodes with zero paths to {target_service}.",
            "target_inbound_calls_count": tgt_inbound_count,
            "reachable_nodes_count": len(visited),
            "citations": []
        }


# =============================================================================
# 3. In-degree Ranking for Functions
# =============================================================================

def rank_functions_by_inbound_calls(
    repo_id: str,
    repo_path: str,
    top_k: int = 20
) -> Dict[str, Any]:
    """
    Ranks top K functions across the entire repository by inbound CALLS degree.
    Produces deterministic sorted metrics with exact call counts and file locations.
    """
    nodes, forward_adj, reverse_adj = _extract_graph_adjacency(repo_id, repo_path, relations=("CALLS",))

    ranked_items = []
    for nid, callers in reverse_adj.items():
        node = nodes.get(nid, {})
        labels = node.get("labels", [])
        if "Function" in labels or "Method" in labels:
            # Count unique or total inbound calls
            call_count = len(callers)
            sp = node.get("source_path", "")
            name = node.get("name", nid)
            line = node.get("start_line", 1)
            ranked_items.append({
                "function_id": nid,
                "name": name,
                "source_path": sp,
                "line": line,
                "inbound_calls": call_count,
                "citation": f"{sp}:{line}"
            })

    # Sort deterministically: highest calls first, then name, then path
    ranked_items.sort(key=lambda x: (-x["inbound_calls"], x["name"], x["source_path"]))
    top_ranked = ranked_items[:top_k]

    for rank, item in enumerate(top_ranked, 1):
        item["rank"] = rank

    return {
        "top_k": top_k,
        "total_ranked_functions": len(ranked_items),
        "rankings": top_ranked
    }


# =============================================================================
# 4. Transitive Dependency Traversal (Distinguishing Imports vs Calls)
# =============================================================================

def compute_transitive_dependencies(
    repo_id: str,
    repo_path: str,
    target_service: str = "payments"
) -> Dict[str, Any]:
    """
    Computes both upstream and downstream transitive dependencies for target_service,
    strictly distinguishing IMPORTS from CALLS.
    """
    nodes, forward_adj, _ = _extract_graph_adjacency(
        repo_id, repo_path, relations=("CALLS", "IMPORTS")
    )

    import_edges: Dict[str, Set[str]] = defaultdict(set)
    call_edges: Dict[str, Set[str]] = defaultdict(set)
    service_citations: Dict[Tuple[str, str, str], List[str]] = defaultdict(list)

    for src, tgts in forward_adj.items():
        src_node = nodes.get(src, {})
        src_sp = src_node.get("source_path", "")
        if "services/" in src_sp:
            src_svc = src_sp.split("services/")[1].split("/")[0]
            for tgt, rel in tgts:
                tgt_node = nodes.get(tgt, {})
                tgt_sp = tgt_node.get("source_path", "")
                if "services/" in tgt_sp:
                    tgt_svc = tgt_sp.split("services/")[1].split("/")[0]
                    if src_svc != tgt_svc:
                        if rel == "IMPORTS":
                            import_edges[src_svc].add(tgt_svc)
                            service_citations[(src_svc, tgt_svc, "IMPORTS")].append(f"{src_sp}:{src_node.get('start_line', 1)}")
                        elif rel == "CALLS":
                            call_edges[src_svc].add(tgt_svc)
                            service_citations[(src_svc, tgt_svc, "CALLS")].append(f"{src_sp}:{src_node.get('start_line', 1)}")

    # Downstream BFS: What target_service depends on (target -> ... -> X)
    def _traverse_forward(edge_map: Dict[str, Set[str]], start: str) -> Tuple[Set[str], Set[str]]:
        direct = set(edge_map.get(start, set()))
        transitive = set()
        queue = deque(sorted(direct))
        visited = set(direct) | {start}
        while queue:
            curr = queue.popleft()
            transitive.add(curr)
            for nxt in sorted(edge_map.get(curr, set())):
                if nxt not in visited:
                    visited.add(nxt)
                    queue.append(nxt)
        return direct, transitive

    # Upstream BFS: What services depend on target_service (X -> ... -> target)
    def _traverse_backward(edge_map: Dict[str, Set[str]], target: str) -> Tuple[Set[str], Set[str]]:
        rev_map: Dict[str, Set[str]] = defaultdict(set)
        for s, tgts in edge_map.items():
            for t in tgts:
                rev_map[t].add(s)
        direct = set(rev_map.get(target, set()))
        transitive = set()
        queue = deque(sorted(direct))
        visited = set(direct) | {target}
        while queue:
            curr = queue.popleft()
            transitive.add(curr)
            for parent in sorted(rev_map.get(curr, set())):
                if parent not in visited:
                    visited.add(parent)
                    queue.append(parent)
        return direct, transitive

    downstream_direct_imports, downstream_trans_imports = _traverse_forward(import_edges, target_service)
    downstream_direct_calls, downstream_trans_calls = _traverse_forward(call_edges, target_service)

    upstream_direct_imports, upstream_trans_imports = _traverse_backward(import_edges, target_service)
    upstream_direct_calls, upstream_trans_calls = _traverse_backward(call_edges, target_service)

    # Collect citations
    citations = []
    for (s, t, rel), c_list in service_citations.items():
        if s == target_service or t == target_service:
            citations.extend(c_list[:2])

    return {
        "target_service": target_service,
        "downstream": {
            "direct_imports": sorted(list(downstream_direct_imports)),
            "direct_calls": sorted(list(downstream_direct_calls)),
            "transitive_imports": sorted(list(downstream_trans_imports)),
            "transitive_calls": sorted(list(downstream_trans_calls))
        },
        "upstream_dependent_services": {
            "direct_importers": sorted(list(upstream_direct_imports)),
            "direct_callers": sorted(list(upstream_direct_calls)),
            "transitive_import_dependents": sorted(list(upstream_trans_imports)),
            "transitive_call_dependents": sorted(list(upstream_trans_calls))
        },
        "citations": sorted(list(set(citations)))
    }


# =============================================================================
# 5. Reverse-Reachability Change Impact Analysis
# =============================================================================

def compute_change_impact_analysis(
    repo_id: str,
    repo_path: str,
    target_module: str = "services.inventory.repository"
) -> Dict[str, Any]:
    """
    Traverses dependencies in the reverse direction (upstream callers/importers)
    from target_module to identify all directly and transitively affected services and tests.
    Returns deduplicated affected services and tests with supporting dependency paths.
    """
    nodes, _, reverse_adj = _extract_graph_adjacency(
        repo_id, repo_path, relations=("CALLS", "IMPORTS", "DEPENDS_ON")
    )

    # Normalize target module path
    target_rel_path = target_module.replace(".", "/")
    if not target_rel_path.endswith(".py"):
        target_file_pattern = target_rel_path + ".py"
    else:
        target_file_pattern = target_rel_path

    # Locate initial seed nodes belonging to target module
    seed_nodes = [
        nid for nid, n in nodes.items()
        if target_file_pattern in n.get("source_path", "") or target_rel_path in n.get("source_path", "")
    ]

    direct_callers: List[Dict[str, Any]] = []
    direct_importers: List[Dict[str, Any]] = []
    direct_affected_services: Set[str] = set()
    transitive_affected_services: Set[str] = set()
    affected_tests: Set[str] = set()
    dependency_paths: List[List[str]] = []
    citations: Set[str] = set()

    # Find immediate callers and importers
    for nid in seed_nodes:
        for parent_id, rel in reverse_adj.get(nid, []):
            pnode = nodes.get(parent_id, {})
            psp = pnode.get("source_path", "")
            pname = pnode.get("name", parent_id)
            pline = pnode.get("start_line", 1)

            # Avoid self-references within same target file
            if target_file_pattern in psp:
                continue

            citations.add(f"{psp}:{pline}")
            item = {
                "symbol": pname,
                "source_path": psp,
                "line": pline,
                "relation": rel
            }
            if rel == "CALLS":
                direct_callers.append(item)
            else:
                direct_importers.append(item)

            if "services/" in psp:
                svc = psp.split("services/")[1].split("/")[0]
                direct_affected_services.add(svc)
            elif "tests/" in psp:
                affected_tests.add(psp)

    # Reverse BFS traversal to discover all transitive dependents
    queue = deque()
    visited: Set[str] = set(seed_nodes)
    node_paths: Dict[str, List[str]] = {}

    for nid in seed_nodes:
        node_paths[nid] = [target_module]

    for nid in seed_nodes:
        for parent_id, rel in reverse_adj.get(nid, []):
            pnode = nodes.get(parent_id, {})
            psp = pnode.get("source_path", "")
            if target_file_pattern not in psp and parent_id not in visited:
                visited.add(parent_id)
                pname = pnode.get("name", parent_id)
                path = [target_module, f"{pname} ({psp})"]
                node_paths[parent_id] = path
                queue.append(parent_id)

    while queue:
        curr_id = queue.popleft()
        curr_path = node_paths.get(curr_id, [])

        curr_node = nodes.get(curr_id, {})
        curr_sp = curr_node.get("source_path", "")
        if "services/" in curr_sp:
            svc = curr_sp.split("services/")[1].split("/")[0]
            transitive_affected_services.add(svc)
        elif "tests/" in curr_sp:
            affected_tests.add(curr_sp)

        for grand_parent_id, rel in reverse_adj.get(curr_id, []):
            if grand_parent_id not in visited:
                visited.add(grand_parent_id)
                gp_node = nodes.get(grand_parent_id, {})
                gp_sp = gp_node.get("source_path", "")
                gp_name = gp_node.get("name", grand_parent_id)
                new_path = curr_path + [f"{gp_name} ({gp_sp})"]
                node_paths[grand_parent_id] = new_path
                queue.append(grand_parent_id)

    # Build representative supporting dependency paths
    sample_services = sorted(list(direct_affected_services | transitive_affected_services))[:8]
    service_paths = []
    for svc in sample_services:
        for nid, p in node_paths.items():
            nd = nodes.get(nid, {})
            sp = nd.get("source_path", "")
            if f"services/{svc}/" in sp and len(p) >= 2:
                service_paths.append(" -> ".join(p[:3]))
                break

    return {
        "target_module": target_module,
        "direct_callers": direct_callers,
        "direct_importers": direct_importers,
        "direct_affected_services": sorted(list(direct_affected_services)),
        "transitively_affected_services": sorted(list(transitive_affected_services)),
        "affected_services": sorted(list(direct_affected_services | transitive_affected_services)),
        "affected_tests": sorted(list(affected_tests)),
        "supporting_dependency_paths": service_paths,
        "citations": sorted(list(citations))
    }
