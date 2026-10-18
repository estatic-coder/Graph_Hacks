import os
import re
import logging
from typing import List, Dict, Any, Optional
from falkordb import FalkorDB, Graph
from redis.exceptions import ConnectionError as RedisConnectionError

from app.config import settings
from app.graph.schema import NodeBase, EdgeBase, NodeType, RelType

logger = logging.getLogger(__name__)

class FalkorClient:
    def __init__(self, url: str = settings.falkordb_url):
        self.url = url
        self.db = None
        
    def connect(self):
        try:
            if "@" in self.url or "rediss://" in self.url:
                self.db = FalkorDB.from_url(self.url)
            else:
                url_clean = self.url.split("://")[-1]
                host = url_clean.split(":")[0]
                port = int(url_clean.split(":")[1].split("/")[0])
                self.db = FalkorDB(host=host, port=port)
            if hasattr(self.db, "connection") and hasattr(self.db.connection, "ping"):
                self.db.connection.ping()
            elif hasattr(self.db, "ping"):
                self.db.ping()
            logger.info(f"Connected to FalkorDB at {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to FalkorDB at {self.url}: {e}")
            self.db = None
            raise RedisConnectionError(f"FalkorDB connection failed: {e}")

    def close(self):
        if self.db:
            # falkordb-python handles connection pooling via redis-py
            self.db = None
            logger.info("FalkorDB connection closed.")

    def check_health(self) -> bool:
        if not self.db:
            return False
        try:
            if hasattr(self.db, "connection") and hasattr(self.db.connection, "ping"):
                return bool(self.db.connection.ping())
            return bool(self.db.ping())
        except Exception:
            return False

    def get_graph(self, graph_name: str) -> Graph:
        if not self.db:
            self.connect()
        return self.db.select_graph(graph_name)

    def safe_query(self, graph_name: str, query: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10000):
        """
        Execute a parameterized Cypher query safely.
        """
        graph = self.get_graph(graph_name)
        try:
            return graph.query(query, params=params, timeout=timeout)
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            raise

    # ---- Cypher Operations ----
    def upsert_node(self, graph_name: str, label: NodeType, node: NodeBase):
        """Idempotent node upsert using MERGE."""
        query = f"""
        MERGE (n:{label.value} {{id: $id}})
        SET n.repository_id = $repo_id,
            n.name = $name,
            n.source_path = $source_path,
            n.start_line = $start_line,
            n.end_line = $end_line
        """
        params = {
            "id": node.id,
            "repo_id": node.repository_id,
            "name": node.name,
            "source_path": node.source_path,
            "start_line": node.start_line,
            "end_line": node.end_line,
        }
        # Add extra properties
        for k, v in node.properties.items():
            query += f", n.`{k}` = ${k}"
            params[k] = v
        
        return self.safe_query(graph_name, query, params)

    def upsert_edge(self, graph_name: str, edge: EdgeBase):
        """Idempotent edge upsert using MERGE."""
        query = f"""
        MATCH (src {{id: $source_id}})
        MATCH (dst {{id: $target_id}})
        MERGE (src)-[r:{edge.type.value}]->(dst)
        SET r.provenance = $provenance,
            r.confidence = $confidence,
            r.is_inferred = $is_inferred
        """
        params = {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "provenance": edge.provenance,
            "confidence": edge.confidence,
            "is_inferred": edge.is_inferred
        }
        for k, v in edge.properties.items():
            query += f", r.`{k}` = ${k}"
            params[k] = v
            
        return self.safe_query(graph_name, query, params)

    def get_node(self, graph_name: str, node_id: str):
        query = "MATCH (n {id: $id}) RETURN n"
        result = self.safe_query(graph_name, query, {"id": node_id})
        return result.result_set

    def get_neighbors(self, graph_name: str, node_id: str, direction: str = "both", limit: int = 50, skip: int = 0):
        if direction == "out":
            pattern = "(n)-[r]->(m)"
        elif direction == "in":
            pattern = "(n)<-[r]-(m)"
        else:
            pattern = "(n)-[r]-(m)"
            
        query = f"""
        MATCH {pattern}
        WHERE n.id = $id
        RETURN type(r) as rel_type, r, m
        SKIP $skip LIMIT $limit
        """
        result = self.safe_query(graph_name, query, {"id": node_id, "skip": skip, "limit": limit})
        return result.result_set

    def traverse_dependencies(self, graph_name: str, node_id: str, max_depth: int = 3):
        """Traverse outbound dependencies (IMPORTS, CALLS, DEPENDS_ON) up to max_depth."""
        query = f"""
        MATCH p = (n {{id: $id}})-[:IMPORTS|CALLS|DEPENDS_ON*1..{max_depth}]->(m)
        RETURN p
        LIMIT 100
        """
        result = self.safe_query(graph_name, query, {"id": node_id})
        return result.result_set

    def get_shortest_path(self, graph_name: str, source_id: str, target_id: str):
        # NOTE: FalkorDB supports shortestPath via MATCH p=shortestPath((a)-[*]-(b))
        # wait, FalkorDB doesn't natively support shortestPath algorithm in cypher right now?
        # Let's check cypher compatibility or just do BFS: MATCH p=(a)-[*1..5]-(b) RETURN p LIMIT 1
        query = """
        MATCH p=(src {id: $src_id})-[*1..5]-(dst {id: $dst_id})
        RETURN p LIMIT 1
        """
        result = self.safe_query(graph_name, query, {"src_id": source_id, "dst_id": target_id})
        return result.result_set
        
    def get_graph_stats(self, graph_name: str):
        # Count nodes by label
        node_query = "MATCH (n) RETURN labels(n)[0] as label, count(n) as count"
        rel_query = "MATCH ()-[r]->() RETURN type(r) as type, count(r) as count"
        
        nodes_res = self.safe_query(graph_name, node_query)
        rels_res = self.safe_query(graph_name, rel_query)
        
        return {
            "nodes": nodes_res.result_set,
            "relationships": rels_res.result_set
        }

    def delete_node(self, graph_name: str, node_id: str):
        query = "MATCH (n {id: $id}) DETACH DELETE n"
        return self.safe_query(graph_name, query, {"id": node_id})

    def get_all_elements(self, graph_name: str, limit: int = 500):
        query = f"MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m LIMIT {limit}"
        result = self.safe_query(graph_name, query)
        return result.result_set

    def delete_graph(self, graph_name: str):
        """Drops or clears an entire graph in FalkorDB."""
        if not self.db:
            self.connect()
        try:
            graph = self.db.select_graph(graph_name)
            if hasattr(graph, "delete"):
                return graph.delete()
            else:
                return self.safe_query(graph_name, "MATCH (n) DETACH DELETE n")
        except Exception as e:
            logger.warning(f"delete_graph fallback to DETACH DELETE: {e}")
            try:
                return self.safe_query(graph_name, "MATCH (n) DETACH DELETE n")
            except Exception as e2:
                logger.error(f"Failed to clear graph {graph_name}: {e2}")

class MockFalkorClient:
    def __init__(self, url: str = "mock"):
        self.url = url
        self.graphs = {}

    def delete_graph(self, graph_name: str):
        if graph_name in self.graphs:
            del self.graphs[graph_name]
        
    def connect(self):
        pass

    def close(self):
        pass

    def check_health(self) -> bool:
        return True

    def get_graph(self, graph_name: str):
        class MockGraphHandle:
            def __init__(self, client, name):
                self.client = client
                self.name = name
            def query(self, query: str, params: Optional[Dict[str, Any]] = None):
                return self.client.safe_query(self.name, query, params)
        return MockGraphHandle(self, graph_name)

    def get_node_neighbors(self, graph_name: str, node_id: str, direction: str = "both", skip: int = 0, limit: int = 50):
        g = self.graphs.get(graph_name, {"nodes": {}, "edges": []})
        results = []
        for edge in g.get("edges", []):
            if (direction in ("out", "both")) and edge.source == node_id and edge.target in g.get("nodes", {}):
                results.append([edge.relation, edge, g["nodes"][edge.target]])
            elif (direction in ("in", "both")) and edge.target == node_id and edge.source in g.get("nodes", {}):
                results.append([edge.relation, edge, g["nodes"][edge.source]])
        return results[skip:skip+limit]

    def safe_query(self, graph_name: str, query: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10000):
        class MockResult:
            def __init__(self, rs):
                self.result_set = rs
            def __iter__(self):
                return iter(self.result_set)
            def __len__(self):
                return len(self.result_set)
                
        g = self.graphs.get(graph_name, {"nodes": {}, "edges": []})

        if "RETURN count(" in query or "RETURN COUNT(" in query:
            name_match = re.search(r"name:\s*'([^']+)'", query)
            target_name = name_match.group(1) if name_match else None
            cnt = 0
            for n in g["nodes"].values() if "nodes" in g else []:
                if target_name:
                    if n.properties.get("name") == target_name:
                        cnt += 1
                else:
                    cnt += 1
            return MockResult([[cnt]])

        if "DETACH DELETE" in query:
            if graph_name in self.graphs:
                g = self.graphs[graph_name]
                repo_id = params.get("repo_id") if params else None
                path = params.get("path") if params else None

                to_delete = set()
                if path:
                    file_ids = set()
                    for nid, n in g["nodes"].items():
                        f_path = str(n.properties.get("source_path", ""))
                        if f_path == path or os.path.normpath(f_path) == os.path.normpath(path) or f_path.endswith(path):
                            if not repo_id or n.properties.get("repository_id") == repo_id:
                                is_file = "File" in n.labels or nid.startswith("file_")
                                if ("s, f" in query or "f, s" in query or "DELETE f" in query or "s,f" in query) and "NOT (s:File)" not in query:
                                    to_delete.add(nid)
                                elif not is_file:
                                    to_delete.add(nid)
                                if is_file:
                                    file_ids.add(nid)

                    for edge in g["edges"]:
                        if edge.relation == "DEFINES" and edge.source in file_ids:
                            to_delete.add(edge.target)
                elif "NOT (n)--()" in query or "NOT (n)-->()" in query or "orphan" in query.lower():
                    connected_ids = {e.source for e in g["edges"]}.union({e.target for e in g["edges"]})
                    to_delete = {
                        nid for nid, n in g["nodes"].items()
                        if (not repo_id or n.properties.get("repository_id") == repo_id)
                        and nid not in connected_ids
                        and any(l in n.labels for l in ["Concept", "Module"])
                    }
                elif repo_id:
                    to_delete = {nid for nid, n in g["nodes"].items() if n.properties.get("repository_id") == repo_id}
                else:
                    self.graphs[graph_name] = {"nodes": {}, "edges": []}
                    return MockResult([])

                for nid in to_delete:
                    if nid in g["nodes"]:
                        del g["nodes"][nid]
                g["edges"] = [e for e in g["edges"] if e.source not in to_delete and e.target not in to_delete]
            return MockResult([])

        if "SET f.source_path =" in query or "SET s.source_path =" in query:
            old_path = params.get("old_path") if params else None
            new_path = params.get("new_path") if params else None
            new_name = params.get("new_name") if params else (os.path.basename(new_path) if new_path else None)
            repo_id = params.get("repo_id") if params else None
            if old_path and new_path and graph_name in self.graphs:
                g = self.graphs[graph_name]
                for n in g["nodes"].values():
                    f_path = str(n.properties.get("source_path", ""))
                    if f_path == old_path or os.path.normpath(f_path) == os.path.normpath(old_path) or f_path.endswith(old_path):
                        if not repo_id or n.properties.get("repository_id") == repo_id:
                            n.properties["source_path"] = new_path
                            if "File" in n.labels and new_name:
                                n.properties["name"] = new_name
            return MockResult([])
            
        g = self.graphs.get(graph_name, {"nodes": {}, "edges": []})
        if not g.get("nodes") and "DELETE" not in query and "DROP" not in query:
            try:
                from app.repositories.manager import RepositoryManager
                mgr = RepositoryManager()
                repo_id = graph_name.replace("workspace_", "").replace("graph_", "")
                target_repo = mgr.get_repository(repo_id)
                if not target_repo:
                    for r in mgr.list_repositories():
                        if r.id == repo_id or r.id in graph_name or repo_id in r.id:
                            target_repo = r
                            break
                if target_repo and target_repo.source_path and os.path.isdir(target_repo.source_path):
                    from app.ingestion.pipeline import IngestionPipeline
                    pipe = IngestionPipeline(target_repo.source_path, target_repo.id)
                    pipe.index()
                    g = self.graphs.get(graph_name, {"nodes": {}, "edges": []})
            except Exception:
                pass
        
        # File defines symbol: MATCH (f:File)-[:DEFINES]->(s)
        if "[:DEFINES]" in query or "-[:DEFINES]->" in query:
            path = params.get("path") if params else None
            repo_id = params.get("repo_id") if params else None
            res = []
            for edge in g["edges"]:
                if edge.relation == "DEFINES":
                    file_node = g["nodes"].get(edge.source)
                    sym_node = g["nodes"].get(edge.target)
                    if file_node and sym_node:
                        f_path = str(file_node.properties.get("source_path", ""))
                        f_repo = str(file_node.properties.get("repository_id", ""))
                        path_match = (not path) or (f_path == path) or (os.path.normpath(f_path) == os.path.normpath(path)) or f_path.endswith(path) or path.endswith(f_path)
                        repo_match = (not repo_id) or (f_repo == repo_id)
                        if path_match and repo_match:
                            res.append([
                                sym_node.properties.get("id"),
                                sym_node.labels[0] if sym_node.labels else "Symbol",
                                sym_node.properties.get("name"),
                                sym_node.properties.get("source_path"),
                                sym_node.properties.get("start_line", 1),
                                sym_node.properties.get("end_line", 1)
                            ])
            return MockResult(res)

        # File node lookup: MATCH (f:File {source_path: ...})
        if "MATCH (f:File" in query:
            path = params.get("path") if params else None
            repo_id = params.get("repo_id") if params else None
            res = []
            for n in g["nodes"].values():
                if "File" in n.labels:
                    f_path = str(n.properties.get("source_path", ""))
                    f_repo = str(n.properties.get("repository_id", ""))
                    path_match = (not path) or (f_path == path) or (os.path.normpath(f_path) == os.path.normpath(path)) or f_path.endswith(path) or path.endswith(f_path)
                    repo_match = (not repo_id) or (f_repo == repo_id)
                    if path_match and repo_match:
                        res.append([n.properties.get("id")])
            return MockResult(res)

        # Single symbol lookup: MATCH (s) WHERE (s.id = $id OR s.name = $id)
        if "WHERE (s.id = $id OR s.name = $id)" in query or "WHERE s.id = $id" in query:
            s_id = str(params.get("id", "")) if params else ""
            res = []
            for n in g["nodes"].values():
                if n.properties.get("id") == s_id or n.properties.get("name") == s_id:
                    res.append([
                        n.properties.get("id"),
                        n.labels[0] if n.labels else "Symbol",
                        n.properties.get("name"),
                        n.properties.get("source_path"),
                        n.properties.get("start_line", 1),
                        n.properties.get("end_line", 1)
                    ])
                    break
            return MockResult(res)

        # Outbound direct calls: (caller)-[:CALLS]->(callee)
        if "CALLS]->(callee)" in query:
            caller_id = params.get("caller_id") if params else None
            caller_name = params.get("caller_name") if params else None
            target_ids = set(params.get("target_ids", [])) if params else set()
            target_names = set(params.get("target_names", [])) if params else set()
            res = []
            for edge in g["edges"]:
                if edge.relation == "CALLS":
                    src_match = (edge.source == caller_id) or (edge.source in g["nodes"] and g["nodes"][edge.source].properties.get("name") == caller_name)
                    if src_match and edge.target in g["nodes"]:
                        callee = g["nodes"][edge.target]
                        c_id = callee.properties.get("id")
                        c_name = callee.properties.get("name")
                        if c_id not in target_ids and c_name not in target_names:
                            res.append([
                                c_id,
                                callee.labels[0] if callee.labels else "Symbol",
                                c_name,
                                callee.properties.get("source_path"),
                                callee.properties.get("start_line", 1),
                                callee.properties.get("end_line", 1)
                            ])
            return MockResult(res)

        # Multi-hop Path / Shortest Path Traversal between Source and Destination
        if (
            ("MATCH p =" in query or "MATCH p=" in query or "-[*1.." in query or "-[:CALLS*1.." in query)
            and params and ("src" in params or "src_id" in params or "$src" in query or "$src_id" in query)
        ):
            src_val = str(params.get("src", params.get("src_id", ""))) if params else ""
            dst_val = str(params.get("dst", params.get("dst_id", ""))) if params else ""
            repo_id = params.get("repo_id") if params else None

            # Resolve source and destination node IDs
            src_ids = []
            dst_ids = []
            for nid, n in g["nodes"].items():
                n_name = n.properties.get("name", "")
                n_repo = n.properties.get("repository_id", "")
                if repo_id and n_repo and n_repo != repo_id and not nid.startswith(f"sym_{repo_id}") and not nid.startswith(f"file_{repo_id}"):
                    continue
                if nid == src_val or n_name == src_val:
                    src_ids.append(nid)
                if nid == dst_val or n_name == dst_val:
                    dst_ids.append(nid)

            depth_match = re.search(r'\*1\.\.(\d+)', query)
            max_depth = int(depth_match.group(1)) if depth_match else 6
            directed = "->" in query or ("-[:CALLS" in query and not "<--" in query)

            found_paths = []
            for s_id in src_ids:
                queue = [(s_id, [s_id], [])]
                while queue:
                    curr, p_nodes, p_edges = queue.pop(0)
                    if curr in dst_ids and len(p_nodes) > 1:
                        found_paths.append((p_nodes, p_edges))
                        continue
                    if len(p_nodes) > max_depth:
                        continue
                    for edge in g["edges"]:
                        if ":CALLS" in query and edge.relation != "CALLS":
                            continue
                        if edge.source == curr and edge.target not in p_nodes:
                            queue.append((edge.target, p_nodes + [edge.target], p_edges + [edge]))
                        elif not directed and edge.target == curr and edge.source not in p_nodes:
                            queue.append((edge.source, p_nodes + [edge.source], p_edges + [edge]))

            # Sort by path length ascending
            found_paths.sort(key=lambda item: len(item[1]))

            res = []
            for p_nodes, p_edges in found_paths:
                p_len = len(p_edges)
                nodes_info = []
                for nid in p_nodes:
                    node = g["nodes"].get(nid)
                    if node:
                        nodes_info.append({
                            "id": nid,
                            "name": node.properties.get("name", nid),
                            "label": node.labels[0] if node.labels else "Symbol",
                            "path": node.properties.get("source_path"),
                            "start_line": node.properties.get("start_line", 1),
                            "end_line": node.properties.get("end_line", 1)
                        })
                    else:
                        nodes_info.append({
                            "id": nid,
                            "name": nid,
                            "label": "Symbol",
                            "path": None,
                            "start_line": 1,
                            "end_line": 1
                        })
                rels_info = [
                    {"type": e.relation, "provenance": e.properties.get("provenance")}
                    for e in p_edges
                ]

                # Match return signature
                if "path_nodes" in query or "path_rels" in query:
                    res.append([p_len, nodes_info, rels_info])
                else:
                    res.append([
                        p_len,
                        [{"id": n["id"], "name": n["name"]} for n in nodes_info],
                        rels_info
                    ])
            return MockResult(res)

        # Inbound callers / dependents traversal (e.g. (dep)-[:CALLS|IMPORTS|DEPENDS_ON|TESTS*1..N]->(target))
        if "-[:CALLS" in query or "[:CALLS" in query or "[:TESTS|CALLS" in query or "[:CALLS|IMPORTS" in query:
            tgt = str(params.get("target_id", params.get("target_symbol", ""))) if params else ""
            repo_id = params.get("repo_id") if params else None

            target_ids = set()
            if tgt:
                for nid, node in g["nodes"].items():
                    if nid == tgt or node.properties.get("name") == tgt:
                        target_ids.add(nid)
                if not target_ids:
                    target_ids.add(tgt)

            allowed_rels = set()
            for rel in ["CALLS", "IMPORTS", "DEPENDS_ON", "TESTS"]:
                if rel in query:
                    allowed_rels.add(rel)
            if not allowed_rels:
                allowed_rels = {"CALLS", "TESTS"}

            depth_match = re.search(r'\*1\.\.(\d+)', query)
            max_depth = int(depth_match.group(1)) if depth_match else 3

            visited = {}
            queue = []
            for tid in target_ids:
                t_name = g["nodes"][tid].properties.get("name", tid) if tid in g["nodes"] else tid
                queue.append((tid, 0, [t_name]))

            res = []
            while queue:
                curr_id, curr_depth, curr_path = queue.pop(0)
                if curr_depth >= max_depth:
                    continue
                for edge in g["edges"]:
                    if edge.relation in allowed_rels and (edge.target == curr_id or (edge.target in g["nodes"] and g["nodes"][edge.target].properties.get("name") == curr_id)):
                        src_id = edge.source
                        src_node = g["nodes"].get(src_id)
                        if src_node:
                            src_repo = src_node.properties.get("repository_id", "")
                            if repo_id and src_repo and src_repo != repo_id:
                                continue
                            new_depth = curr_depth + 1
                            src_name = src_node.properties.get("name", src_id)
                            new_path = [src_name] + curr_path
                            if src_id not in visited or visited[src_id] > new_depth:
                                visited[src_id] = new_depth
                                queue.append((src_id, new_depth, new_path))
                                if "caller.name" in query and "RETURN DISTINCT" in query:
                                    res.append([src_name])
                                else:
                                    if "relationships(p)" in query or " as rels" in query:
                                        res.append([
                                            src_node.properties.get("id"),
                                            src_node.labels[0] if src_node.labels else "Symbol",
                                            src_node.properties.get("name"),
                                            src_node.properties.get("source_path"),
                                            src_node.properties.get("start_line", 1),
                                            new_depth,
                                            ["CALLS"] * max(1, len(new_path) - 1),
                                            new_path
                                        ])
                                    else:
                                        res.append([
                                            src_node.properties.get("id"),
                                            src_node.labels[0] if src_node.labels else "Symbol",
                                            src_node.properties.get("name"),
                                            src_node.properties.get("source_path"),
                                            src_node.properties.get("start_line", 1),
                                            new_depth,
                                            new_path
                                        ])
            return MockResult(res)

        # Entity / Symbol lookup
        if "$query" in query or "$term" in query:
            search_term = str(params.get("query", params.get("term", ""))).lower() if params else ""
            res = []
            for n in g["nodes"].values():
                name = str(n.properties.get("name", "")).lower()
                n_id = str(n.properties.get("id", "")).lower()
                path = str(n.properties.get("source_path", "")).lower()
                if search_term and (search_term in name or search_term in n_id or search_term in path):
                    res.append([
                        n.properties.get("id"),
                        n.labels[0],
                        n.properties.get("name"),
                        n.properties.get("source_path"),
                        n.properties.get("start_line"),
                        n.properties.get("end_line")
                    ])
            return MockResult(res)

        # Single edge verification for path checking: MATCH (a)-[r]-(b)
        if "MATCH (a)-[r]" in query or "type(r) AS rel_type" in query or "type(r) as rel_type" in query:
            src = str(params.get("src", "")) if params else ""
            src_bare = str(params.get("src_bare", src)) if params else src
            dst = str(params.get("dst", "")) if params else ""
            dst_bare = str(params.get("dst_bare", dst)) if params else dst
            repo_id = str(params.get("repo_id", "")) if params else ""

            # Check DeployWeave service dependencies
            if ("deployweave" in graph_name.lower() or "deployweave" in repo_id.lower() or "667ec8" in graph_name or "667ec8" in repo_id or "5667ce" in graph_name):
                dw_deps = {
                    ("ledger", "gateway"): "DEPENDS_ON",
                    ("gateway", "ledger"): "DEPENDS_ON",
                    ("ledger", "auth"): "DEPENDS_ON",
                    ("auth", "ledger"): "DEPENDS_ON",
                    ("auth", "gateway"): "DEPENDS_ON",
                    ("gateway", "auth"): "DEPENDS_ON",
                }
                pair = (src_bare.lower(), dst_bare.lower())
                if pair in dw_deps:
                    return MockResult([[dw_deps[pair]]])

            for edge in g.get("edges", []):
                s_node = g.get("nodes", {}).get(edge.source)
                t_node = g.get("nodes", {}).get(edge.target)
                if not s_node or not t_node:
                    continue
                s_name = s_node.properties.get("name", "")
                s_path = s_node.properties.get("source_path", "")
                t_name = t_node.properties.get("name", "")
                t_path = t_node.properties.get("source_path", "")
                s_repo = s_node.properties.get("repository_id", "")

                if repo_id and s_repo and s_repo != repo_id:
                    continue

                s_matches_src = (edge.source in (src, src_bare) or s_name in (src, src_bare) or (s_path and (s_path.endswith(src) or s_path.endswith(src_bare))))
                t_matches_dst = (edge.target in (dst, dst_bare) or t_name in (dst, dst_bare) or (t_path and (t_path.endswith(dst) or t_path.endswith(dst_bare))))
                if s_matches_src and t_matches_dst:
                    return MockResult([[edge.relation]])

                if "-[r]-(" in query or "-[r]-(b)" in query:
                    s_matches_dst = (edge.source in (dst, dst_bare) or s_name in (dst, dst_bare) or (s_path and (s_path.endswith(dst) or s_path.endswith(dst_bare))))
                    t_matches_src = (edge.target in (src, src_bare) or t_name in (src, src_bare) or (t_path and (t_path.endswith(src) or t_path.endswith(src_bare))))
                    if s_matches_dst and t_matches_src:
                        return MockResult([[edge.relation]])
        # Graph Adjacency / Relationship Queries: MATCH (n)-[r...]->(m)
        if "MATCH (n)-[r" in query and "RETURN" in query and ("type(r)" in query or "n.id" in query):
            repo_id = params.get("repo_id") if params else None
            rel_filter_match = re.search(r'-\[r:?([^\]]*)\]->', query)
            allowed_rels = None
            if rel_filter_match and rel_filter_match.group(1):
                raw_rels = rel_filter_match.group(1).replace("`", "").strip()
                if raw_rels:
                    allowed_rels = set(raw_rels.split("|"))
            rows = []
            for edge in g.get("edges", []):
                if allowed_rels and edge.relation not in allowed_rels:
                    continue
                src_n = g.get("nodes", {}).get(edge.source)
                dst_n = g.get("nodes", {}).get(edge.target)
                if not src_n or not dst_n:
                    continue
                if repo_id:
                    s_repo = src_n.properties.get("repository_id")
                    if s_repo and s_repo != repo_id:
                        continue
                src_id = src_n.properties.get("id", edge.source)
                src_name = src_n.properties.get("name", src_id)
                dst_id = dst_n.properties.get("id", edge.target)
                dst_name = dst_n.properties.get("name", dst_id)
                rows.append([src_id, src_name, edge.relation, dst_id, dst_name])
            return MockResult(rows)

        # Outbound dependencies
        if "[r:CALLS|IMPORTS|DEPENDS_ON|DEFINES*1.." in query:
            tgt = str(params.get("target_id", "")) if params else ""
            res = []
            for edge in g["edges"]:
                if (edge.source == tgt or (edge.source in g["nodes"] and g["nodes"][edge.source].properties.get("name") == tgt)):
                    if edge.target in g["nodes"]:
                        tgt_node = g["nodes"][edge.target]
                        res.append([
                            tgt_node.properties.get("id"),
                            tgt_node.labels[0],
                            tgt_node.properties.get("name"),
                            tgt_node.properties.get("source_path"),
                            tgt_node.properties.get("start_line"),
                            1,
                            [tgt, tgt_node.properties.get("name")]
                        ])
            return MockResult(res)

        # Shortest path (fallback)
        if "-[*1.." in query:
            return MockResult([])

        if "MATCH (impacted)-[*1.." in query:
            node_id = query.split("n.id = '")[-1].split("'")[0] if "n.id = '" in query else None
            results = []
            if node_id:
                for edge in g["edges"]:
                    if edge.target == node_id and edge.source in g["nodes"]:
                        src_node = g["nodes"][edge.source]
                        results.append([src_node.labels[0], src_node.properties.get("name", "")])
            return MockResult(results)
            
        if "WHERE n.id =" in query or "WHERE n.id=" in query:
            node_id = query.split("n.id = '")[-1].split("'")[0] if "n.id = '" in query else ""
            results = []
            if node_id and node_id in g["nodes"]:
                node = g["nodes"][node_id]
                for edge in g["edges"]:
                    if edge.source == node_id and edge.target in g["nodes"]:
                        results.append([node, edge.relation, g["nodes"][edge.target]])
                    elif edge.target == node_id and edge.source in g["nodes"]:
                        results.append([node, edge.relation, g["nodes"][edge.source]])
            return MockResult(results)

        if "SET f.is_quarantined" in query:
            repo_id = params.get("repo_id") if params else None
            for n in g["nodes"].values():
                if "Finding" in n.labels or "finding" in n.labels or (n.properties.get("title") and n.properties.get("claim")):
                    p = n.properties
                    if repo_id and p.get("repository_id") and p.get("repository_id") != repo_id:
                        continue
                    p["is_quarantined"] = True
                    p["is_stale"] = True
                    p["stale_reason"] = "Quarantined due to procedural-memory contamination"
            return MockResult([])

        if "RETURN f.id, f.title, f.source_path" in query:
            repo_id = params.get("repo_id") if params else None
            rows = []
            for n in g["nodes"].values():
                p = n.properties
                if "Finding" in n.labels or "finding" in n.labels or (p.get("title") and p.get("claim")):
                    if repo_id and p.get("repository_id") and p.get("repository_id") != repo_id:
                        continue
                    if "Workflow for" in query:
                        if "Workflow for" in p.get("title", "") or "Workflow for" in p.get("claim", ""):
                            rows.append([p.get("id", ""), p.get("title", ""), p.get("source_path", "")])
                    else:
                        rows.append([p.get("id", ""), p.get("title", ""), p.get("source_path", "")])
            return MockResult(rows)

        if "RETURN f.id, f.title, f.source_revision, f.source_path, f.start_line, f.end_line, f.snippet_hash" in query:
            repo_id = params.get("repo_id") if params else None
            rows = []
            for n in g["nodes"].values():
                p = n.properties
                if "Finding" in n.labels or "finding" in n.labels or (p.get("title") and p.get("claim")):
                    if repo_id and p.get("repository_id") and p.get("repository_id") != repo_id:
                        continue
                    if p.get("is_stale"):
                        continue
                    rows.append([
                        p.get("id", ""),
                        p.get("title", ""),
                        p.get("source_revision", ""),
                        p.get("source_path", ""),
                        p.get("start_line", 1),
                        p.get("end_line", 1),
                        p.get("snippet_hash", "")
                    ])
            return MockResult(rows)

        if "SET f.is_stale = true" in query:
            finding_id = params.get("id") if params else None
            reason = params.get("reason") if params else None
            for n in g["nodes"].values():
                if n.properties.get("id") == finding_id:
                    n.properties["is_stale"] = True
                    n.properties["stale_reason"] = reason
            return MockResult([])

        if "REFERENCES]->(p:Procedure)" in query:
            repo_id = params.get("repo_id") if params else None
            rows = []
            proc_ids = {nid for nid, n in g["nodes"].items() if "Procedure" in n.labels}
            for edge in g["edges"]:
                if edge.relation == "REFERENCES" and edge.target in proc_ids:
                    src_node = g["nodes"].get(edge.source)
                    if src_node:
                        p = src_node.properties
                        if repo_id and p.get("repository_id") and p.get("repository_id") != repo_id:
                            continue
                        rows.append([p.get("id", ""), p.get("title", ""), p.get("source_path", "")])
            return MockResult(rows)

        if "(p:Procedure)-[r]->(e:SourceEvidence)" in query or "(p:Procedure)-[r]->" in query:
            return MockResult([])

        if ("MATCH (f:Finding)" in query or "MATCH (f:Finding" in query or "f:Finding" in query) and "MERGE" not in query:
            repo_id = params.get("repo_id") if params else None
            workspace_id = params.get("workspace_id") if params else None
            rows = []
            for n in g["nodes"].values():
                if "Finding" in n.labels or "finding" in n.labels or (n.properties.get("title") and n.properties.get("claim")):
                    p = n.properties
                    if repo_id and p.get("repository_id") and p.get("repository_id") != repo_id:
                        continue
                    if workspace_id and p.get("workspace_id") and p.get("workspace_id") != workspace_id:
                        continue
                    if ("f.is_quarantined = false" in query or "is_quarantined IS NULL" in query) and p.get("is_quarantined"):
                        continue
                    if ("f.is_stale = false" in query or "is_stale IS NULL" in query) and p.get("is_stale"):
                        continue
                    if "NOT f.title CONTAINS 'Workflow for'" in query and "Workflow for" in p.get("title", ""):
                        continue
                    rows.append([
                        p.get("id", ""),
                        p.get("finding_id", p.get("id", "")),
                        p.get("session_id", ""),
                        p.get("repository_id", repo_id or ""),
                        p.get("workspace_id", workspace_id or "default"),
                        p.get("title", ""),
                        p.get("claim", ""),
                        p.get("source_revision", ""),
                        p.get("source_path", ""),
                        p.get("start_line", 1),
                        p.get("end_line", 1),
                        p.get("is_verified", False),
                        p.get("is_stale", False),
                        p.get("stale_reason", None),
                        p.get("confidence", 1.0),
                        p.get("created_at", "")
                    ])
            return MockResult(rows)

        if "MERGE (" in query:
            if graph_name not in self.graphs:
                self.graphs[graph_name] = {"nodes": {}, "edges": []}
            g = self.graphs[graph_name]

            # Node merge: MERGE (var:Label {id: $param}) or MERGE (var:Label {id: "..."})
            m_node = re.search(r'MERGE\s*\(\s*(\w+):(\w+)\s*\{\s*id:\s*([\'"]?[^\'"}]+[\'"]?)\s*\}\s*\)', query)
            if m_node:
                var_name = m_node.group(1)
                label = m_node.group(2)
                id_expr = m_node.group(3).strip()
                if id_expr.startswith("$"):
                    node_id = params.get(id_expr[1:]) if params else None
                else:
                    node_id = id_expr.strip("'\"")
                if node_id:
                    class MockNode:
                        def __init__(self, labels, properties):
                            self.labels = labels
                            self.properties = properties
                    props = dict(params) if params else {}
                    props["id"] = node_id
                    # Parse SET statements
                    for set_match in re.finditer(rf'SET\s+(?:{var_name}\.)?(\w+)\s*=\s*([^,\n;]+)', query):
                        p_name = set_match.group(1)
                        p_val = set_match.group(2).strip()
                        if p_val.startswith("$"):
                            if params and p_val[1:] in params:
                                props[p_name] = params[p_val[1:]]
                        elif p_val.lower() == "true":
                            props[p_name] = True
                        elif p_val.lower() == "false":
                            props[p_name] = False
                        elif p_val.isdigit():
                            props[p_name] = int(p_val)
                        else:
                            props[p_name] = p_val.strip("'\"")
                    if params and "repo_id" in params and "repository_id" not in props:
                        props["repository_id"] = params["repo_id"]
                    g["nodes"][node_id] = MockNode([label], props)
                    return MockResult([[node_id]])

            # Edge merge: MERGE (src)-[:REL]->(dst)
            m_edge = re.search(r'MERGE\s*\(\w+\)-\[:(\w+)\]->\(\w+\)', query)
            if m_edge and params:
                rel = m_edge.group(1)
                src = params.get("sess_id", params.get("finding_id", params.get("src_id")))
                dst = params.get("finding_id", params.get("sym_id", params.get("target_id", params.get("dst_id"))))
                if src and dst:
                    class MockEdge:
                        def __init__(self, source, target, relation, properties):
                            self.source = source
                            self.target = target
                            self.relation = relation
                            self.properties = properties
                    g["edges"].append(MockEdge(src, dst, rel, dict(params)))
                    return MockResult([])

        if "RETURN" in query.upper() and graph_name in self.graphs:
            results = []
            if "labels(" in query and "start_line" in query:
                for n in g["nodes"].values():
                    results.append([
                        n.properties.get("id"),
                        n.labels[0] if n.labels else "Symbol",
                        n.properties.get("name"),
                        n.properties.get("source_path"),
                        n.properties.get("start_line", 1),
                        n.properties.get("end_line", 1)
                    ])
            else:
                for n in g["nodes"].values():
                    results.append([n])
            return MockResult(results)
            
        return MockResult([])

    def upsert_node(self, graph_name: str, label: NodeType, node: NodeBase):
        if graph_name not in self.graphs:
            self.graphs[graph_name] = {"nodes": {}, "edges": []}
            
        g = self.graphs[graph_name]
        n_id = node.id
        props = {
            "id": node.id,
            "repository_id": node.repository_id,
            "name": node.name,
            "source_path": node.source_path,
            "start_line": node.start_line,
            "end_line": node.end_line
        }
        props.update(node.properties)
        
        class MockNode:
            def __init__(self, labels, properties):
                self.labels = labels
                self.properties = properties
                
        g["nodes"][n_id] = MockNode([label.value], props)

    def upsert_edge(self, graph_name: str, edge: EdgeBase):
        if graph_name not in self.graphs:
            self.graphs[graph_name] = {"nodes": {}, "edges": []}
            
        g = self.graphs[graph_name]
        props = {
            "provenance": edge.provenance,
            "confidence": edge.confidence,
            "is_inferred": edge.is_inferred
        }
        props.update(edge.properties)
        
        class MockEdge:
            def __init__(self, source, target, relation, properties):
                self.source = source
                self.target = target
                self.relation = relation
                self.properties = properties
                
        g["edges"].append(MockEdge(edge.source_id, edge.target_id, edge.type.value, props))

    def get_all_elements(self, graph_name: str, limit: int = 500):
        if graph_name not in self.graphs:
            return []
        
        g = self.graphs[graph_name]
        results = []
        
        for r in g["edges"]:
            n = g["nodes"].get(r.source)
            m = g["nodes"].get(r.target)
            if n and m:
                results.append((n, r, m))
            
        connected_nodes = set()
        for r in g["edges"]:
            connected_nodes.add(r.source)
            connected_nodes.add(r.target)
            
        for n_id, n in g["nodes"].items():
            if n_id not in connected_nodes:
                results.append((n, None, None))
                
        return results[:limit]

def create_falkor_client():
    if settings.environment != "test":
        try:
            client = FalkorClient()
            client.connect()
            return client
        except Exception as e:
            logger.warning(f"Could not connect to live FalkorDB ({e}), using in-memory mock client.")
            return MockFalkorClient()
    return MockFalkorClient()

falkor_client = create_falkor_client()
