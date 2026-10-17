import os
import pytest
from app.agent.verifier import EvidenceVerifier
from app.agent.investigator import GraphInvestigator

SAMPLE_REPO_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../sample-repo"))

@pytest.fixture(scope="module")
def setup_graph():
    from app.ingestion.pipeline import IngestionPipeline
    pipeline = IngestionPipeline(repo_path=SAMPLE_REPO_PATH, repo_id="sample_1")
    pipeline.index()
    return pipeline

def test_verify_valid_citations():
    verifier = EvidenceVerifier(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    text = """
    The function is defined in `utils.py` (Lines 1–4).
    Refer to `db.py:9-13` for the database query implementation.
    """
    report = verifier.verify(text)
    assert report.is_verified is True
    assert report.citations_checked >= 2
    assert report.citations_valid >= 2
    assert len(report.fabricated_citations) == 0

def test_reject_fabricated_citations():
    verifier = EvidenceVerifier(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # 1. Nonexistent file
    text_fake_file = "Authentication is handled in `auth_service.py` (Lines 10–25)."
    report_fake = verifier.verify(text_fake_file)
    assert report_fake.is_verified is False
    assert len(report_fake.fabricated_citations) == 1
    assert "NONEXISTENT_FILE" in report_fake.fabricated_citations[0].rejection_reason

    # 2. Line number out of bounds
    text_oob = "Check `main.py` (Lines 500–550) for route definitions."
    report_oob = verifier.verify(text_oob)
    assert report_oob.is_verified is False
    assert len(report_oob.fabricated_citations) == 1
    assert "LINE_OUT_OF_BOUNDS" in report_oob.fabricated_citations[0].rejection_reason

    # 3. Path traversal attack
    text_traversal = "System config in `../../etc/passwd` (Lines 1–5)."
    report_trav = verifier.verify(text_traversal)
    assert report_trav.is_verified is False
    assert len(report_trav.fabricated_citations) == 1
    assert "FABRICATED_PATH" in report_trav.fabricated_citations[0].rejection_reason

def test_verify_valid_graph_paths(setup_graph):
    verifier = EvidenceVerifier(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Valid call chain in sample-repo: read_user -> get_user -> get_db_connection -> load_config
    valid_text = """
    Verified relationship:
    - `read_user -> get_user -> get_db_connection -> load_config`
    """
    report = verifier.verify(valid_text)
    assert report.is_verified is True
    assert report.paths_checked == 1
    assert report.paths_valid == 1
    assert len(report.fabricated_paths) == 0

def test_reject_nonexistent_graph_paths(setup_graph):
    verifier = EvidenceVerifier(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Nonexistent path: test_format_user_data does NOT call load_config directly
    fake_path_text = """
    Path trace:
    - `test_format_user_data -> load_config`
    - `read_user -> imaginary_payment_processor`
    """
    report = verifier.verify(fake_path_text)
    assert report.is_verified is False
    assert report.paths_checked == 2
    assert len(report.fabricated_paths) >= 1
    assert any("NONEXISTENT_RELATIONSHIP" in p.rejection_reason for p in report.fabricated_paths)

def test_distinguish_extracted_vs_inferred():
    verifier = EvidenceVerifier(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    text = """
    ### Evidence & Inferences
    - **[Extracted]** Verified 1 graph traversal path(s) in FalkorDB.
    - **[Extracted]** `get_user` is defined as `Function` in `db.py` (lines 9-13).
    - **[Inferred]** Changes to this symbol require regression testing across all identified callers.
    - **[Inferred]** We recommend adding an index to the database.
    """
    report = verifier.verify(text)
    assert len(report.extracted_evidence) >= 2
    assert len(report.inferred_claims) >= 2
    assert any("db.py" in e for e in report.extracted_evidence)
    assert any("recommend" in inf or "require" in inf for inf in report.inferred_claims)

def test_explicit_insufficient_evidence_reporting(setup_graph):
    verifier = EvidenceVerifier(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    pipeline_data = {
        "insufficient_evidence_reason": "No automated test coverage found in FalkorDB for 'quantum_validator'."
    }
    text = "> **Insufficient Evidence**: No automated test coverage found in FalkorDB for 'quantum_validator'."
    
    report = verifier.verify(text, pipeline_data=pipeline_data)
    assert len(report.insufficient_evidence_flags) >= 1
    assert "quantum_validator" in report.insufficient_evidence_flags[0]

def test_investigator_applies_verification_rejection_alert(setup_graph):
    investigator = GraphInvestigator(repo_id="sample_1", repo_path=SAMPLE_REPO_PATH)
    
    # Fabricate a response with nonexistent citations and nonexistent graph paths
    fake_raw = """
    Here is the architecture:
    - `read_user -> imaginary_bitcoin_miner`
    Source file is in `nonexistent_crypto_vault.py` (Lines 10–20).
    """
    pdata = {"graph_paths": [], "insufficient_evidence_reason": "No evidence"}
    report = investigator.verifier.verify(fake_raw, pdata)
    sealed_output = investigator._apply_verification_seal(fake_raw, report, pdata)
    
    assert "Verification Rejection Alert" in sealed_output
    assert "Rejected Citation" in sealed_output
    assert "Rejected Graph Path" in sealed_output
