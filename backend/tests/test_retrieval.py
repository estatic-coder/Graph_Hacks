import os
import tempfile
import shutil
import pytest
from fastapi.testclient import TestClient

from app.services.retrieval import CodeTokenizer, HybridRetriever
from app.ingestion.pipeline import IngestionPipeline
from app.main import app

@pytest.fixture
def test_repo_env():
    tmp_dir = tempfile.mkdtemp(prefix="asterion_retrieval_test_")
    repo_id = "test_retrieval_repo"

    f1 = os.path.join(tmp_dir, "payment.py")
    with open(f1, "w") as f:
        f.write('''
def process_payment(amount: float, card_number: str):
    """Processes credit card payment and handles checkout transactions."""
    validated = validate_card(card_number)
    if not validated:
        raise ValueError("Invalid card")
    return True

def validate_card(card_number: str) -> bool:
    """Validates credit card checksum using Luhn algorithm."""
    return len(card_number) == 16
''')

    f2 = os.path.join(tmp_dir, "tax.py")
    with open(f2, "w") as f:
        f.write('''
def calculate_vat(subtotal: float, rate: float = 0.2) -> float:
    """Calculates value-added tax for invoice items."""
    return subtotal * rate
''')

    # Index into graph
    pipeline = IngestionPipeline(tmp_dir, repo_id)
    pipeline.index(incremental=False)

    yield {"repo_id": repo_id, "repo_path": tmp_dir}

    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_code_tokenizer():
    tokens = CodeTokenizer.tokenize("parseTypeScript(user_order.id, OrderService)")
    assert "parsetypescript" in tokens or "parse" in tokens
    assert "type" in tokens
    assert "script" in tokens
    assert "user" in tokens
    assert "order" in tokens
    assert "orderservice" in tokens or "service" in tokens


def test_bm25_lexical_retrieval(test_repo_env):
    retriever = HybridRetriever(
        repo_id=test_repo_env["repo_id"],
        repo_path=test_repo_env["repo_path"]
    )
    res = retriever.retrieve("process payment transaction checkout", limit=5, expand_graph=False)
    assert res["returned_items"] > 0
    top_item = res["items"][0]
    assert "process_payment" in top_item["name"] or "payment.py" in top_item["source_path"]
    assert top_item["bm25_score"] > 0.0


def test_hybrid_graph_expansion(test_repo_env):
    retriever = HybridRetriever(
        repo_id=test_repo_env["repo_id"],
        repo_path=test_repo_env["repo_path"]
    )
    res = retriever.retrieve("process payment", limit=5, expand_graph=True)
    assert res["returned_items"] > 0
    
    # Check that hybrid score combines BM25 and graph scores
    for it in res["items"]:
        assert 0.0 <= it["hybrid_score"] <= 1.0
        assert "rrf_score" in it
        assert "neighbors" in it


def test_token_budget_enforcement(test_repo_env):
    retriever = HybridRetriever(
        repo_id=test_repo_env["repo_id"],
        repo_path=test_repo_env["repo_path"]
    )
    # Strict 120 token budget
    res = retriever.retrieve("payment tax invoice card", limit=10, max_tokens=120)
    assert res["estimated_tokens"] <= 120
    assert res["budget_used_pct"] <= 100.0
    assert len(res["context_text"]) > 0


def test_api_retrieve_endpoints(test_repo_env):
    client = TestClient(app)
    
    # GET endpoint
    r_get = client.get(f"/api/retrieve?repo_id={test_repo_env['repo_id']}&query=calculate%20vat&limit=3")
    assert r_get.status_code == 200
    data_get = r_get.json()
    assert data_get["status"] == "success"
    assert data_get["data"]["returned_items"] > 0

    # POST endpoint
    payload = {
        "repo_id": test_repo_env["repo_id"],
        "query": "validate card checksum",
        "limit": 2,
        "max_tokens": 1000,
        "alpha": 0.7
    }
    r_post = client.post("/api/retrieve", json=payload)
    assert r_post.status_code == 200
    data_post = r_post.json()
    assert data_post["status"] == "success"
    assert data_post["data"]["returned_items"] > 0
