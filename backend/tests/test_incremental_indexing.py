import os
import tempfile
import shutil
import pytest
from app.ingestion.incremental import IncrementalIndexer
from app.graph.client import falkor_client

@pytest.fixture
def temp_repo():
    tmp_dir = tempfile.mkdtemp(prefix="asterion_test_incremental_")
    repo_id = "test_inc_repo"
    
    # Create initial files
    f1 = os.path.join(tmp_dir, "service.py")
    with open(f1, "w") as f:
        f.write("""
def process_data(item: str):
    return item.strip()
""")
        
    f2 = os.path.join(tmp_dir, "utils.py")
    with open(f2, "w") as f:
        f.write("""
def helper_func():
    return 42
""")

    yield {"repo_id": repo_id, "repo_path": tmp_dir}
    
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_cold_and_incremental_skip(temp_repo):
    repo_id = temp_repo["repo_id"]
    repo_path = temp_repo["repo_path"]
    indexer = IncrementalIndexer(repo_id=repo_id, repo_path=repo_path)
    
    # 1. Cold index
    res1 = indexer.index_incrementally()
    assert res1["files_processed"] == 2
    assert res1["parsed_symbols"] >= 2
    assert res1["is_incremental"] is False
    
    # 2. Immediate second scan - all unchanged
    res2 = indexer.index_incrementally()
    assert res2["is_incremental"] is True
    assert res2["files_skipped_unchanged"] == 2
    assert res2["files_processed"] == 0


def test_incremental_add_and_modify(temp_repo):
    repo_id = temp_repo["repo_id"]
    repo_path = temp_repo["repo_path"]
    indexer = IncrementalIndexer(repo_id=repo_id, repo_path=repo_path)
    indexer.index_incrementally()
    
    # Add new file
    f3 = os.path.join(repo_path, "handlers.py")
    with open(f3, "w") as f:
        f.write("def handle_request(): pass\n")
        
    res_add = indexer.index_incrementally()
    assert res_add["added_count"] == 1
    assert res_add["files_processed"] == 1
    assert res_add["files_skipped_unchanged"] == 2
    
    # Modify service.py
    f1 = os.path.join(repo_path, "service.py")
    with open(f1, "w") as f:
        f.write("def process_data(item: str): return item.upper()\ndef new_func(): pass\n")
        
    res_mod = indexer.index_incrementally()
    assert res_mod["modified_count"] == 1
    assert res_mod["files_processed"] == 1
    assert res_mod["files_skipped_unchanged"] == 2


def test_rename_and_delete(temp_repo):
    repo_id = temp_repo["repo_id"]
    repo_path = temp_repo["repo_path"]
    indexer = IncrementalIndexer(repo_id=repo_id, repo_path=repo_path)
    indexer.index_incrementally()
    
    # Rename utils.py to tools.py
    old_p = os.path.join(repo_path, "utils.py")
    new_p = os.path.join(repo_path, "tools.py")
    os.rename(old_p, new_p)
    
    scan = indexer.scan_repository()
    assert len(scan["renamed"]) == 1
    assert scan["renamed"][0]["old_path"] == "utils.py"
    assert scan["renamed"][0]["new_path"] == "tools.py"
    
    res_rename = indexer.index_incrementally()
    assert res_rename["renamed_count"] == 1
    assert res_rename["files_skipped_unchanged"] == 1  # service.py unchanged
    
    # Delete tools.py
    os.remove(new_p)
    res_del = indexer.index_incrementally()
    assert res_del["deleted_count"] == 1
    assert res_del["files_skipped_unchanged"] == 1


def test_hash_persistence(temp_repo):
    repo_id = temp_repo["repo_id"]
    repo_path = temp_repo["repo_path"]
    hash_file = os.path.join(repo_path, ".asterion_hashes.json")
    
    indexer1 = IncrementalIndexer(repo_id=repo_id, repo_path=repo_path, hash_storage_path=hash_file)
    indexer1.index_incrementally()
    
    assert os.path.isfile(hash_file)
    
    # New indexer instance loads hashes from file
    indexer2 = IncrementalIndexer(repo_id=repo_id, repo_path=repo_path, hash_storage_path=hash_file)
    assert len(indexer2._file_hashes) == 2
    res = indexer2.index_incrementally()
    assert res["files_processed"] == 0
    assert res["files_skipped_unchanged"] == 2
