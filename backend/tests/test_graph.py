import pytest
from app.graph.client import FalkorClient
from app.graph.schema import NodeBase, EdgeBase, NodeType, RelType
from redis.exceptions import ConnectionError as RedisConnectionError

client = FalkorClient(url="redis://localhost:6379")

def is_db_available():
    try:
        client.connect()
        return client.check_health()
    except Exception:
        return False
        
pytestmark = pytest.mark.skipif(not is_db_available(), reason="FalkorDB is not available")

def test_upsert_and_retrieve_node():
    graph_name = "test_asterion_graph"
    node = NodeBase(
        id="file_1",
        repository_id="repo_test",
        name="main.py",
        source_path="/src/main.py"
    )
    
    # Clean up before
    try:
        client.safe_query(graph_name, "MATCH (n) DELETE n")
    except Exception:
        pass
        
    client.upsert_node(graph_name, NodeType.FILE, node)
    
    # Retrieve
    res = client.get_node(graph_name, "file_1")
    assert len(res) == 1
    # Check properties
    retrieved_node = res[0][0] # first row, first column
    # The dictionary of properties can be checked
    props = getattr(retrieved_node, 'properties', None) or {}
    assert props.get('id') == "file_1"
    assert props.get('name') == "main.py"

def test_upsert_edge_and_neighbors():
    graph_name = "test_asterion_graph"
    
    node1 = NodeBase(id="file_2", repository_id="repo_test", name="app.py", source_path="/src/app.py")
    node2 = NodeBase(id="class_1", repository_id="repo_test", name="App", source_path="/src/app.py")
    
    client.upsert_node(graph_name, NodeType.FILE, node1)
    client.upsert_node(graph_name, NodeType.CLASS, node2)
    
    edge = EdgeBase(source_id="file_2", target_id="class_1", type=RelType.DEFINES, confidence=1.0, is_inferred=False)
    client.upsert_edge(graph_name, edge)
    
    # Neighbors
    res = client.get_neighbors(graph_name, "file_2", direction="out")
    assert len(res) == 1
    rel_type = res[0][0]
    assert rel_type == "DEFINES"

def test_graph_stats():
    graph_name = "test_asterion_graph"
    stats = client.get_graph_stats(graph_name)
    assert "nodes" in stats
    assert "relationships" in stats

def test_traverse_dependencies_and_shortest_path():
    graph_name = "test_asterion_graph"
    
    node_a = NodeBase(id="mod_a", repository_id="repo_test", name="moduleA", source_path="/a.py")
    node_b = NodeBase(id="mod_b", repository_id="repo_test", name="moduleB", source_path="/b.py")
    node_c = NodeBase(id="mod_c", repository_id="repo_test", name="moduleC", source_path="/c.py")
    
    client.upsert_node(graph_name, NodeType.MODULE, node_a)
    client.upsert_node(graph_name, NodeType.MODULE, node_b)
    client.upsert_node(graph_name, NodeType.MODULE, node_c)
    
    client.upsert_edge(graph_name, EdgeBase(source_id="mod_a", target_id="mod_b", type=RelType.IMPORTS))
    client.upsert_edge(graph_name, EdgeBase(source_id="mod_b", target_id="mod_c", type=RelType.IMPORTS))
    
    # Traverse
    res = client.traverse_dependencies(graph_name, "mod_a", max_depth=2)
    assert len(res) > 0  # Should find paths
    
    # Shortest path
    path = client.get_shortest_path(graph_name, "mod_a", "mod_c")
    assert len(path) > 0

def test_delete_node():
    graph_name = "test_asterion_graph"
    client.upsert_node(graph_name, NodeType.FILE, NodeBase(id="delete_me", repository_id="repo", name="del"))
    client.delete_node(graph_name, "delete_me")
    res = client.get_node(graph_name, "delete_me")
    assert len(res) == 0
