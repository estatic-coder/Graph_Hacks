import pytest
from unittest.mock import MagicMock, patch
from app.graph.client import FalkorClient
from app.graph.schema import NodeBase, EdgeBase, NodeType, RelType
from redis.exceptions import ConnectionError as RedisConnectionError

@pytest.fixture
def mock_client():
    client = FalkorClient(url="redis://localhost:6379")
    client.db = MagicMock()
    return client

def test_client_connect_failure():
    client = FalkorClient(url="redis://invalid:6379")
    with patch('app.graph.client.FalkorDB') as mock_falkor:
        mock_falkor.side_effect = Exception("Connection refused")
        with pytest.raises(RedisConnectionError):
            client.connect()

def test_upsert_node_query_generation(mock_client):
    node = NodeBase(
        id="file_1",
        repository_id="repo_test",
        name="main.py",
        source_path="/src/main.py"
    )
    
    mock_graph = MagicMock()
    mock_client.db.select_graph.return_value = mock_graph
    
    mock_client.upsert_node("test_graph", NodeType.FILE, node)
    
    # Check if query was called with correct parameters
    mock_graph.query.assert_called_once()
    args, kwargs = mock_graph.query.call_args
    query = args[0]
    params = kwargs['params']
    
    assert "MERGE (n:File {id: $id})" in query
    assert params["id"] == "file_1"
    assert params["name"] == "main.py"
    assert params["source_path"] == "/src/main.py"

def test_upsert_edge_query_generation(mock_client):
    edge = EdgeBase(
        source_id="file_1",
        target_id="func_1",
        type=RelType.DEFINES
    )
    
    mock_graph = MagicMock()
    mock_client.db.select_graph.return_value = mock_graph
    
    mock_client.upsert_edge("test_graph", edge)
    
    mock_graph.query.assert_called_once()
    args, kwargs = mock_graph.query.call_args
    query = args[0]
    params = kwargs['params']
    
    assert "MERGE (src)-[r:DEFINES]->(dst)" in query
    assert params["source_id"] == "file_1"
    assert params["target_id"] == "func_1"
    assert params["confidence"] == 1.0

def test_shortest_path_query(mock_client):
    mock_graph = MagicMock()
    mock_client.db.select_graph.return_value = mock_graph
    
    mock_client.get_shortest_path("test_graph", "a", "b")
    
    mock_graph.query.assert_called_once()
    args, kwargs = mock_graph.query.call_args
    query = args[0]
    
    assert "MATCH p=(src {id: $src_id})-[*1..5]-(dst {id: $dst_id})" in query

def test_delete_node(mock_client):
    mock_graph = MagicMock()
    mock_client.db.select_graph.return_value = mock_graph
    
    mock_client.delete_node("test_graph", "file_1")
    
    mock_graph.query.assert_called_once()
    args, kwargs = mock_graph.query.call_args
    assert "DETACH DELETE n" in args[0]

def test_traverse_dependencies_query(mock_client):
    mock_graph = MagicMock()
    mock_client.db.select_graph.return_value = mock_graph
    
    mock_client.traverse_dependencies("test_graph", "file_1")
    
    mock_graph.query.assert_called_once()
    args, kwargs = mock_graph.query.call_args
    assert "[:IMPORTS|CALLS|DEPENDS_ON*1..3]" in args[0]
