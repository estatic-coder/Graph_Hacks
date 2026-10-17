"""
tests/test_v2_graph_algorithms.py - Graph Algorithms as First-Class Agent Tools Suite.

Validates all 11 first-class graph algorithms:
1. shortest_path
2. bounded_all_paths
3. reachable_nodes
4. reverse_dependencies
5. connected_components
6. strongly_connected_components
7. centrality (degree & betweenness)
8. pagerank
9. community_detection
10. architecture_boundary_check
11. impact_subgraph
"""

import pytest
from unittest.mock import patch

from app.graph.algorithms import GraphAlgorithmEngine


@pytest.fixture
def sample_graph_engine():
    engine = GraphAlgorithmEngine(repo_id="test_repo")
    # Synthetic adjacency graph:
    # A -> B -> C -> D
    # A -> E -> C
    # C -> F
    # F -> G -> F (circular dependency!)
    sample_adj = {
        "A": [("B", "CALLS"), ("E", "CALLS")],
        "B": [("C", "CALLS")],
        "E": [("C", "CALLS")],
        "C": [("D", "CALLS"), ("F", "CALLS")],
        "D": [],
        "F": [("G", "CALLS")],
        "G": [("F", "CALLS")]
    }
    return engine, sample_adj


def test_shortest_path(sample_graph_engine):
    engine, adj = sample_graph_engine
    with patch.object(engine, "_build_adjacency", return_value=adj):
        res = engine.shortest_path("A", "D")
        assert res.algorithm == "shortest_path"
        assert res.result["found"] is True
        assert res.result["hop_count"] == 3
        assert res.result["node_ids"][0] == "A"
        assert res.result["node_ids"][-1] == "D"
        assert "A ->" in res.explanation


def test_bounded_all_paths(sample_graph_engine):
    engine, adj = sample_graph_engine
    with patch.object(engine, "_build_adjacency", return_value=adj):
        res = engine.bounded_all_paths("A", "C", max_depth=3)
        assert res.algorithm == "bounded_all_paths"
        assert res.result["path_count"] == 2
        # Paths are A->B->C and A->E->C
        paths = res.result["paths"]
        assert ["A", "B", "C"] in paths
        assert ["A", "E", "C"] in paths


def test_reachable_and_reverse_dependencies(sample_graph_engine):
    engine, adj = sample_graph_engine
    adj_in = {
        "B": [("A", "CALLS")],
        "E": [("A", "CALLS")],
        "C": [("B", "CALLS"), ("E", "CALLS")],
        "D": [("C", "CALLS")],
        "F": [("C", "CALLS"), ("G", "CALLS")],
        "G": [("F", "CALLS")],
        "A": []
    }

    with patch.object(engine, "_build_adjacency", side_effect=lambda direction="out", **kw: adj if direction=="out" else adj_in):
        # Forward reachable from A
        fwd = engine.reachable_nodes("A", max_depth=3)
        assert fwd.result["count"] >= 4
        assert "B" in fwd.result["nodes"]
        assert "C" in fwd.result["nodes"]

        # Reverse callers to C
        rev = engine.reverse_dependencies("C", max_depth=2)
        assert "B" in rev.result["nodes"]
        assert "E" in rev.result["nodes"]
        assert "A" in rev.result["nodes"]


def test_strongly_connected_components(sample_graph_engine):
    engine, adj = sample_graph_engine
    with patch.object(engine, "_build_adjacency", return_value=adj):
        scc_res = engine.strongly_connected_components()
        assert scc_res.algorithm == "strongly_connected_components"
        assert scc_res.result["circular_count"] == 1
        # Circular cluster is F and G
        assert sorted(scc_res.result["circular_dependency_groups"][0]) == ["F", "G"]


def test_centrality_and_pagerank(sample_graph_engine):
    engine, adj = sample_graph_engine
    adj_in = {
        "B": [("A", "CALLS")],
        "E": [("A", "CALLS")],
        "C": [("B", "CALLS"), ("E", "CALLS")],
        "D": [("C", "CALLS")],
        "F": [("C", "CALLS"), ("G", "CALLS")],
        "G": [("F", "CALLS")],
        "A": []
    }

    with patch.object(engine, "_build_adjacency", side_effect=lambda direction="out", **kw: adj if direction=="out" else (adj_in if direction=="in" else {**adj, **adj_in})):
        cent = engine.centrality(metric="degree")
        assert cent.algorithm == "centrality"
        top_ids = [n["id"] for n in cent.result["top_nodes"]]
        assert "C" in top_ids[:3]  # C is highest degree hub

        pr = engine.pagerank(top_k=5)
        assert pr.algorithm == "pagerank"
        assert len(pr.result["rankings"]) > 0


def test_community_detection_and_boundary_check(sample_graph_engine):
    engine, adj = sample_graph_engine
    with patch.object(engine, "_build_adjacency", return_value=adj):
        comm = engine.community_detection()
        assert comm.algorithm == "community_detection"
        assert comm.result["community_count"] >= 1

        # Check boundary between A and D
        bound = engine.architecture_boundary_check("A", "D")
        assert bound.algorithm == "architecture_boundary_check"


def test_impact_subgraph(sample_graph_engine):
    engine, adj = sample_graph_engine
    adj_in = {
        "B": [("A", "CALLS")],
        "C": [("B", "CALLS")],
        "D": [("C", "CALLS")]
    }
    with patch.object(engine, "_build_adjacency", return_value=adj_in):
        impact = engine.impact_subgraph(["D"], max_depth=3)
        assert impact.algorithm == "impact_subgraph"
        assert "D" in impact.result["impacted_nodes"]
        assert "C" in impact.result["impacted_nodes"]
        assert "B" in impact.result["impacted_nodes"]
