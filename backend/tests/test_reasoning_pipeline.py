import os
import pytest
from app.agent.intent import IntentClassifier
from app.agent.resolver import EntityResolver
from app.agent.tools import TypedGraphTools
from app.agent.pipeline import ReasoningPipeline
from app.agent.investigator import GraphInvestigator
from app.graph.client import falkor_client

SAMPLE_REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample-repo"))

@pytest.fixture(scope="module")
def setup_graph():
    """Ensure the sample repo is indexed into workspace_sample_1 in FalkorDB."""
    from app.ingestion.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(repo_path=SAMPLE_REPO_PATH, repo_id="sample_1")
    pipeline.index()
    return pipeline

def test_intent_classification():
    classifier = IntentClassifier()

    # Caller tracing
    res1 = classifier.classify("Who calls get_user in the repository?")
    assert res1.intent == "CALLER_TRACING"
    assert "get_user" in res1.candidate_entities

    # Dependency traversal
    res2 = classifier.classify("What does read_user depend on?")
    assert res2.intent == "DEPENDENCY_TRAVERSAL"
    assert "read_user" in res2.candidate_entities

    # Shortest path
    res3 = classifier.classify("What is the shortest path between read_user and load_config?")
    assert res3.intent == "SHORTEST_PATH"
    assert "read_user" in res3.candidate_entities
    assert "load_config" in res3.candidate_entities

    # Test discovery
    res4 = classifier.classify("What tests cover format_user_data?")
    assert res4.intent == "TEST_DISCOVERY"
    assert "format_user_data" in res4.candidate_entities

    # Source inspection
    res5 = classifier.classify("Inspect the source code of get_db_connection")
    assert res5.intent == "SOURCE_INSPECTION"
    assert "get_db_connection" in res5.candidate_entities

def test_entity_resolution(setup_graph):
    resolver = EntityResolver(repo_id="sample_1")
    
    # Resolve get_user
    resolved = resolver.resolve(["get_user"])
    assert len(resolved) >= 1
    top = resolved[0]
    assert top.name == "get_user"
    assert top.source_path == "db.py"
    assert top.type in ("Function", "Node")

    # Resolve format_user_data
    resolved_utils = resolver.resolve(["format_user_data"])
    assert len(resolved_utils) >= 1
    assert resolved_utils[0].name == "format_user_data"
    assert resolved_utils[0].source_path == "utils.py"

    # Resolve file name
    resolved_file = resolver.resolve(["main.py"])
    assert len(resolved_file) >= 1
    assert "main.py" in resolved_file[0].id

def test_typed_graph_tools_symbol_search(setup_graph):
    tools = TypedGraphTools(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    symbols = tools.symbol_search("user")
    assert len(symbols) >= 1
    names = [s["name"] for s in symbols]
    assert any("user" in n for n in names)

def test_typed_graph_tools_trace_callers(setup_graph):
    tools = TypedGraphTools(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Trace who calls format_user_data (should be read_user and test_format_user_data)
    callers_res = tools.trace_callers("format_user_data", max_depth=3)
    caller_names = [c["name"] for c in callers_res["callers"]]
    assert "read_user" in caller_names or "test_format_user_data" in caller_names

def test_typed_graph_tools_traverse_dependencies(setup_graph):
    tools = TypedGraphTools(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Outbound dependencies from read_user
    dep_res = tools.traverse_dependencies("read_user", direction="outbound", max_depth=3)
    dep_names = [d["name"] for d in dep_res["dependencies"]]
    assert "get_user" in dep_names or "format_user_data" in dep_names

def test_typed_graph_tools_shortest_path(setup_graph):
    tools = TypedGraphTools(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    path_res = tools.find_shortest_path("read_user", "load_config", max_depth=5)
    
    if path_res.get("found"):
        assert "read_user" in path_res["path_str"]
        assert "load_config" in path_res["path_str"]

def test_typed_graph_tools_inspect_source():
    tools = TypedGraphTools(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Real source line inspection
    res = tools.inspect_source("utils.py", start_line=1, end_line=5)
    assert "code" in res
    assert "format_user_data" in res["code"]
    assert res["start_line"] == 1
    assert res["file_path"] == "utils.py"

    # Directory traversal prevention
    bad_res = tools.inspect_source("../../etc/passwd")
    assert "error" in bad_res

def test_typed_graph_tools_test_discovery(setup_graph):
    tools = TypedGraphTools(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    test_res = tools.discover_related_tests("format_user_data")
    assert test_res["test_count"] >= 1
    test_names = [t["name"] for t in test_res["tests"]]
    assert "test_format_user_data" in test_names

def test_reasoning_pipeline_end_to_end(setup_graph):
    pipeline = ReasoningPipeline(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Test query
    out = pipeline.run("Who calls get_user in the repository?")
    assert out["intent"] == "CALLER_TRACING"
    assert len(out["resolved_entities"]) >= 1
    assert len(out["source_evidence"]) >= 1
    assert len(out["graph_paths"]) >= 1

def test_insufficient_evidence_reporting(setup_graph):
    pipeline = ReasoningPipeline(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Query for nonexistent entity
    out = pipeline.run("What tests cover imaginary_unicorn_service?")
    assert out["intent"] == "TEST_DISCOVERY"
    assert out["insufficient_evidence_reason"] is not None
    assert "No automated test coverage found" in out["insufficient_evidence_reason"] or "No target entity identified" in out["insufficient_evidence_reason"]

def test_graph_investigator_grounded_answer(setup_graph):
    investigator = GraphInvestigator(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    answer = investigator.investigate("Who calls format_user_data?")
    assert "format_user_data" in answer
    assert "CALLER_TRACING" in answer or "read_user" in answer or "test_format_user_data" in answer
