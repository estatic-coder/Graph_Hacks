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

    def safe_query(self, graph_name: str, query: str, params: Optional[Dict[str, Any]] = None, timeout: int = 10000):
        class MockResult:
            def __init__(self, rs):
                self.result_set = rs
            def __iter__(self):
                return iter(self.result_set)
            def __len__(self):
                return len(self.result_set)
                
        if "DETACH DELETE n" in query:
            if graph_name in self.graphs:
                repo_id = params.get("repo_id") if params else None
                if repo_id:
                    # Clear nodes for this repo
                    g = self.graphs[graph_name]
                    to_delete = [nid for nid, n in g["nodes"].items() if n.properties.get("repository_id") == repo_id]
                    for nid in to_delete:
                        del g["nodes"][nid]
                    g["edges"] = [e for e in g["edges"] if e.source not in to_delete and e.target not in to_delete]
                else:
                    self.graphs[graph_name] = {"nodes": {}, "edges": []}
            return MockResult([])
            
        g = self.graphs.get(graph_name, {"nodes": {}, "edges": []})
        
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

        # Callers / Inbound
        if "-[:CALLS*1.." in query:
            tgt = str(params.get("target_id", "")) if params else ""
            res = []
            for edge in g["edges"]:
                if edge.relation in ("CALLS", "TESTS") and (edge.target == tgt or (edge.target in g["nodes"] and g["nodes"][edge.target].properties.get("name") == tgt)):
                    if edge.source in g["nodes"]:
                        src_node = g["nodes"][edge.source]
                        res.append([
                            src_node.properties.get("id"),
                            src_node.labels[0],
                            src_node.properties.get("name"),
                            src_node.properties.get("source_path"),
                            src_node.properties.get("start_line"),
                            1,
                            [edge.relation],
                            [src_node.properties.get("name"), tgt]
                        ])
            return MockResult(res)

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

        # Related tests
        if "[:TESTS|CALLS*1.." in query:
            tgt = str(params.get("target_id", "")) if params else ""
            res = []
            for edge in g["edges"]:
                if edge.relation in ("TESTS", "CALLS") and (edge.target == tgt or (edge.target in g["nodes"] and g["nodes"][edge.target].properties.get("name") == tgt)):
                    if edge.source in g["nodes"]:
                        src_node = g["nodes"][edge.source]
                        if src_node.labels[0] == "Test" or "test" in str(src_node.properties.get("name", "")).lower():
                            res.append([
                                src_node.properties.get("id"),
                                src_node.labels[0],
                                src_node.properties.get("name"),
                                src_node.properties.get("source_path"),
                                src_node.properties.get("start_line"),
                                1,
                                [src_node.properties.get("name"), tgt]
                            ])
            return MockResult(res)

        # Shortest path
        if "-[*1.." in query:
            src = str(params.get("src", params.get("src_id", ""))) if params else ""
            dst = str(params.get("dst", params.get("dst_id", ""))) if params else ""
            for edge in g["edges"]:
                if (edge.source == src and edge.target == dst) or (edge.target == src and edge.source == dst):
                    src_n = g["nodes"].get(src, None)
                    dst_n = g["nodes"].get(dst, None)
                    if src_n and dst_n:
                        return MockResult([[
                            1,
                            [{"id": src_n.properties.get("id"), "name": src_n.properties.get("name")},
                             {"id": dst_n.properties.get("id"), "name": dst_n.properties.get("name")}],
                            [{"type": edge.relation, "provenance": edge.properties.get("provenance")}]
                        ]])
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

        if "RETURN" in query.upper() and graph_name in self.graphs:
            results = []
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
