import os
import pytest
from unittest.mock import patch, MagicMock
from app.ingestion.pipeline import IngestionPipeline

@pytest.fixture
def sample_repo_path():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '../../sample-repo'))

@patch('app.ingestion.pipeline.falkor_client')
def test_ingestion_pipeline(mock_falkor, sample_repo_path):
    pipeline = IngestionPipeline(repo_path=sample_repo_path, repo_id="sample_1")
    
    stats = pipeline.index()
    
    assert stats["files_scanned"] > 0
    assert stats["symbols_extracted"] > 0
    
    # Verify that falkor_client's upsert functions were called
    assert mock_falkor.upsert_node.called
    assert mock_falkor.upsert_edge.called
