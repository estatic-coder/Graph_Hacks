import os
import pytest
from app.agent.impact import GitDiffParser, ImpactAnalyzer, ImpactAnalysisResult
from fastapi.testclient import TestClient
from app.main import app

SAMPLE_REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample-repo"))

@pytest.fixture(scope="module")
def setup_graph():
    from app.ingestion.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(repo_path=SAMPLE_REPO_PATH, repo_id="sample_1")
    pipeline.index()
    return pipeline

def test_git_diff_parser_unified_format():
    sample_diff = """
diff --git a/db.py b/db.py
index 1234567..89abcdef 100644
--- a/db.py
+++ b/db.py
@@ -9,4 +9,5 @@ def get_user(user_id):
     conn = get_db_connection()
     cursor = conn.cursor()
+    # Added validation check
     cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
     return cursor.fetchone()
"""
    file_diffs = GitDiffParser.parse(sample_diff)
    assert len(file_diffs) == 1
    fd = file_diffs[0]
    assert fd.file_path == "db.py"
    assert len(fd.hunks) == 1
    assert 11 in fd.changed_lines

def test_map_diff_lines_to_graph_symbols(setup_graph):
    analyzer = ImpactAnalyzer(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Diff modifying get_user inside db.py (lines 9-13)
    diff_text = """
--- a/db.py
+++ b/db.py
@@ -10,2 +10,3 @@ def get_user(user_id):
     conn = get_db_connection()
+    print("Audit log access")
     cursor = conn.cursor()
"""
    result = analyzer.analyze(diff_text=diff_text)
    assert len(result.files_changed) == 1
    assert "db.py" in result.files_changed[0]
    
    # Should map directly to Function: get_user
    changed_names = [s.name for s in result.changed_symbols]
    assert "get_user" in changed_names

def test_identify_direct_and_transitive_dependents(setup_graph):
    analyzer = ImpactAnalyzer(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Diff changing load_config in config.py
    diff_config = """
--- a/config.py
+++ b/config.py
@@ -3,3 +3,4 @@
 def load_config():
+    print("Reloading config")
     with open('config.json') as f:
         return json.load(f)
"""
    result = analyzer.analyze(diff_text=diff_config, max_depth=3)
    
    impacted_names = [i.name for i in result.impacted_entities]
    # get_db_connection is direct caller (depth 1)
    assert "get_db_connection" in impacted_names
    # get_user is transitive caller (depth 2)
    assert "get_user" in impacted_names
    # read_user is transitive endpoint caller (depth 3)
    assert "read_user" in impacted_names

def test_discover_connected_apis_and_tests(setup_graph):
    analyzer = ImpactAnalyzer(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Diff modifying format_user_data in utils.py (lines 1-4)
    diff_utils = """
--- a/utils.py
+++ b/utils.py
@@ -1,4 +1,5 @@
 def format_user_data(user_row):
+    # New formatting logic
     if not user_row:
         return None
     return {"id": user_row[0], "name": user_row[1]}
"""
    result = analyzer.analyze(diff_text=diff_utils, max_depth=3)
    
    # Connected API endpoint should be discovered
    assert "read_user" in result.connected_apis or any("read_user" in name for name in result.connected_apis)
    # Connected test should be discovered
    assert "test_format_user_data" in result.connected_tests

def test_transparent_deterministic_scoring():
    analyzer = ImpactAnalyzer(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    diff_text = """
--- a/db.py
+++ b/db.py
@@ -9,4 +9,5 @@
 def get_user(user_id):
+    # change
     conn = get_db_connection()
"""
    result = analyzer.analyze(diff_text=diff_text)
    
    assert result.risk_score > 0.0
    assert result.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    # Score breakdown must be transparent itemized list
    assert len(result.score_breakdown) > 0
    assert any("pts" in item for item in result.score_breakdown)

def test_explain_impact_through_graph_paths(setup_graph):
    analyzer = ImpactAnalyzer(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    diff_text = """
--- a/db.py
+++ b/db.py
@@ -9,4 +9,5 @@
 def get_user(user_id):
+    # change
     conn = get_db_connection()
"""
    result = analyzer.analyze(diff_text=diff_text)
    
    assert len(result.explanations) > 0
    for exp in result.explanations:
        assert "via `" in exp
        assert "->" in exp or "depth" in exp

def test_api_impact_endpoint(setup_graph):
    client = TestClient(app)
    
    diff_payload = {
        "repo_id": "sample_1",
        "diff_text": """
--- a/utils.py
+++ b/utils.py
@@ -1,3 +1,4 @@
 def format_user_data(user_row):
+    # modified
     if not user_row:
""",
        "max_depth": 3
    }
    
    response = client.post("/api/impact", json=diff_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["changed_symbols"]) >= 1
    assert len(data["affected_node_ids"]) >= 1
    assert "risk_score" in data
    assert "connected_tests" in data
