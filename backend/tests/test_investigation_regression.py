import os
import pytest
from typing import Dict, Any

from app.agent.intent import IntentClassifier, IntentResult
from app.agent.resolver import SymbolResolver
from app.agent.impact import ImpactAnalyzer
from app.agent.pipeline import ReasoningPipeline, ErrorState
from app.agent.investigator import GraphInvestigator
from app.agent.verifier import EvidenceVerifier
from app.graph.client import falkor_client

SAMPLE_REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample-repo"))
SENTINEL_REPO_ID = "repo_sentinelshop_ast_e1e991"
SENTINEL_REPO_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../data/repos/repo_sentinelshop_ast_e1e991/SentinelShop")
)

QUERY = (
    "If I modify the payment authorization logic, which order-processing functions, "
    "inventory operations, notifications, and tests could be affected? "
    "Show the dependency paths and source-code evidence."
)

@pytest.fixture(scope="module")
def ensure_sentinel_indexed():
    """Ensures SentinelShop is indexed in FalkorDB if repo directory exists."""
    if os.path.isdir(SENTINEL_REPO_PATH):
        graph = falkor_client.get_graph(f"workspace_{SENTINEL_REPO_ID}")
        res = graph.query("MATCH (n:Function {name: 'authorize_payment'}) RETURN count(n) AS cnt")
        cnt = res.result_set[0][0] if res.result_set else 0
        if cnt == 0:
            from app.ingestion.pipeline import IngestionPipeline
            pipeline = IngestionPipeline(repo_path=SENTINEL_REPO_PATH, repo_id=SENTINEL_REPO_ID)
            pipeline.index()
    return SENTINEL_REPO_ID


def test_multi_intent_classification():
    """
    1. Multi-intent classification:
    - Primary intent is CHANGE_IMPACT_ANALYSIS
    - Secondary intents capture DEPENDENCY_TRAVERSAL, TEST_DISCOVERY, SOURCE_EVIDENCE
    - The presence of the word 'tests' does NOT hijack the primary intent to TEST_DISCOVERY
    - Extracts candidate phrase 'payment authorization logic'
    """
    intent = IntentClassifier().classify(QUERY)
    assert intent.primary_intent == "CHANGE_IMPACT_ANALYSIS"
    assert "DEPENDENCY_TRAVERSAL" in intent.secondary_intents
    assert "TEST_DISCOVERY" in intent.secondary_intents
    assert "SOURCE_EVIDENCE" in intent.secondary_intents
    assert intent.primary_intent != "TEST_DISCOVERY"
    
    # Must capture the natural-language phrase
    assert any("payment authorization" in phrase.lower() for phrase in intent.candidate_phrases)


def test_natural_language_symbol_resolution(ensure_sentinel_indexed):
    """
    2. Natural language symbol resolution:
    - Maps 'payment authorization logic' to `authorize_payment` in `sentinelshop/payments.py`
    - Confidence is high (> 0.8)
    - Ambiguity flag is not set for clear matches
    - Nonexistent / fabricated concept returns empty candidate list without hallucination
    """
    resolver = SymbolResolver(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    candidates = resolver.resolve("payment authorization logic")
    assert len(candidates) >= 1
    top = candidates[0]
    assert top.name == "authorize_payment"
    assert "payments.py" in top.source_path
    assert top.confidence >= 0.8
    assert top.is_ambiguous is False

    # Negative test: Nonexistent entity must NOT be fabricated
    phantom = resolver.resolve("quantum_teleportation_ledger_protocol")
    assert len(phantom) == 0


def test_direct_caller_discovery(ensure_sentinel_indexed):
    """
    3. Direct caller discovery:
    - Identifies `place_order` as the direct caller of `authorize_payment`
    - Filters out File and Module nodes (`orders.py`, `api.py`) from callers list
    """
    analyzer = ImpactAnalyzer(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    resolver = SymbolResolver(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    candidates = resolver.resolve("authorize_payment")
    assert len(candidates) >= 1
    target = candidates[0]

    impact = analyzer.analyze_symbol_impact(target.id, max_depth=3)
    assert "place_order" in impact.direct_callers
    # Ensure raw file/module nodes are not reported as callers
    for dc in impact.direct_callers:
        assert not dc.endswith(".py")


def test_transitive_dependency_discovery(ensure_sentinel_indexed):
    """
    4. Transitive dependency discovery:
    - Identifies `checkout` as an upstream entrypoint / transitive caller
    - Discovers call chain `checkout -> place_order -> authorize_payment`
    """
    analyzer = ImpactAnalyzer(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    resolver = SymbolResolver(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    candidates = resolver.resolve("authorize_payment")
    assert len(candidates) >= 1
    target = candidates[0]

    impact = analyzer.analyze_symbol_impact(target.id, max_depth=3)
    assert "checkout" in impact.transitive_callers
    
    # Check graph paths
    paths = [imp.path for imp in impact.impacted_entities if imp.path]
    transitive_paths = [p for p in paths if "checkout" in p and "place_order" in p]
    assert len(transitive_paths) >= 1


def test_downstream_operations_and_control_flow(ensure_sentinel_indexed):
    """
    5. Distinguishing static callers from control-flow consequences:
    - `reserve_stock` (inventory), `save_order` (persistence), and `send_order_confirmation` (notification)
      are identified as downstream operations executed inside `place_order`
    - NONE of these downstream operations are claimed to be direct callers of `authorize_payment`
    """
    analyzer = ImpactAnalyzer(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    resolver = SymbolResolver(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    candidates = resolver.resolve("authorize_payment")
    assert len(candidates) >= 1
    target = candidates[0]

    impact = analyzer.analyze_symbol_impact(target.id, max_depth=3)
    op_names = [op.name for op in impact.downstream_operations]
    
    assert "reserve_stock" in op_names
    assert "save_order" in op_names
    assert "send_order_confirmation" in op_names

    # CRITICAL: They are downstream execution consequences, NOT direct callers
    assert "reserve_stock" not in impact.direct_callers
    assert "save_order" not in impact.direct_callers
    assert "send_order_confirmation" not in impact.direct_callers


def test_test_discovery(ensure_sentinel_indexed):
    """
    6. Automated test discovery:
    - Direct tests covering `authorize_payment` (`test_payments.py`)
    - Indirect tests covering callers (`test_orders.py`, `test_api.py`)
    - Both direct and indirect test suites are reported
    """
    analyzer = ImpactAnalyzer(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    resolver = SymbolResolver(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    candidates = resolver.resolve("authorize_payment")
    assert len(candidates) >= 1
    target = candidates[0]

    impact = analyzer.analyze_symbol_impact(target.id, max_depth=3)
    all_tests = impact.direct_tests + impact.indirect_tests
    assert len(all_tests) >= 2
    assert any("test_payments.py" in t for t in impact.direct_tests)
    assert any("test_orders.py" in t or "test_api.py" in t for t in impact.indirect_tests)


def test_source_citation_verification(ensure_sentinel_indexed):
    """
    7. Source citation and graph path verification:
    - Validates that source evidence points to existing lines in payments.py, orders.py, etc.
    - EvidenceVerifier verifies all citations and graph paths against disk and FalkorDB
    - Zero fabricated citations or invalid paths
    """
    pipeline = ReasoningPipeline(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    pdata = pipeline.run(QUERY)

    verifier = EvidenceVerifier(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    investigator = GraphInvestigator(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    
    raw_answer = investigator._synthesize_grounded_response(pdata)
    report = verifier.verify(raw_answer, pdata)

    assert report.is_verified is True
    assert len(report.fabricated_citations) == 0
    assert len(report.fabricated_paths) == 0
    assert report.citations_valid >= 1
    assert report.paths_valid >= 1


def test_missing_entity_handling(ensure_sentinel_indexed):
    """
    8. Missing entity handling and distinct error state:
    - When a nonexistent entity is queried, pipeline reports ENTITY_NOT_FOUND
    - Insufficient evidence reason states entity resolution failure
    - Does NOT falsely report 'No automated test coverage found'
    """
    pipeline = ReasoningPipeline(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    pdata = pipeline.run("What order-processing functions break if I change the hyper_warp_drive logic?")

    assert pdata["error_state"] == "ENTITY_NOT_FOUND"
    assert "No automated test coverage found" not in (pdata.get("insufficient_evidence_reason") or "")
    assert "No target entity identified" in pdata["insufficient_evidence_reason"] or "could not be resolved" in pdata["insufficient_evidence_reason"]


def test_repository_isolation(ensure_sentinel_indexed):
    """
    9. Repository isolation:
    - `authorize_payment` exists in SentinelShop graph (`workspace_repo_sentinelshop_ast_e1e991`)
    - `authorize_payment` does NOT exist in sample repo graph (`workspace_sample_1`)
    - Cross-repository query isolation is strictly preserved
    """
    # Sample repo check
    sample_pipeline = ReasoningPipeline(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    sample_data = sample_pipeline.run("What functions call authorize_payment?")
    assert len(sample_data.get("resolved_entities", [])) == 0
    assert sample_data.get("error_state") == "ENTITY_NOT_FOUND"

    # SentinelShop check
    sentinel_pipeline = ReasoningPipeline(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    sentinel_data = sentinel_pipeline.run("What functions call authorize_payment?")
    assert len(sentinel_data.get("resolved_entities", [])) >= 1
    assert sentinel_data["resolved_entities"][0]["name"] == "authorize_payment"
    assert sentinel_data.get("error_state") is None


def test_sentinelshop_end_to_end_investigation(ensure_sentinel_indexed):
    """
    10. End-to-end SentinelShop investigation:
    - Executes `investigate_with_report` on the complete user query
    - Verifies synthesized answer contains all required architectural components:
      * authorize_payment (target)
      * place_order (direct caller)
      * checkout (transitive caller)
      * reserve_stock, save_order, send_order_confirmation (downstream control flow)
      * test suites (test_payments.py, test_orders.py)
      * clear static vs control-flow distinction
    - Formal verification report is 100% verified with 0 rejections
    """
    investigator = GraphInvestigator(repo_id=SENTINEL_REPO_ID, repo_path=SENTINEL_REPO_PATH)
    answer, report = investigator.investigate_with_report(QUERY)

    # Core symbols must be present
    assert "authorize_payment" in answer
    assert "place_order" in answer
    assert "checkout" in answer
    assert "reserve_stock" in answer
    assert "send_order_confirmation" in answer
    assert "test_payments.py" in answer
    assert "test_orders.py" in answer

    # Static vs control flow distinction must be explicitly stated
    assert "Static vs Control Flow Distinction" in answer or "control-flow" in answer.lower()

    # Verification status must be clean
    assert report.is_verified is True
    assert len(report.fabricated_citations) == 0
    assert len(report.fabricated_paths) == 0
    assert "Verified Evidence:" in answer
