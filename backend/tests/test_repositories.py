import os
import io
import zipfile
import tempfile
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.repositories.manager import RepositoryManager

client = TestClient(app)

def test_list_repositories():
    response = client.get("/api/repositories")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "repositories" in data
    assert len(data["repositories"]) >= 1
    
    # Check default demo repo
    demo_repo = next((r for r in data["repositories"] if r["id"] == "sample_1"), None)
    assert demo_repo is not None
    assert demo_repo["is_demo"] is True
    assert demo_repo["name"] == "sample-repo"


def test_import_local_repository():
    # Create a temporary directory with a python file
    with tempfile.TemporaryDirectory() as temp_dir:
        test_file = os.path.join(temp_dir, "calculator.py")
        with open(test_file, "w") as f:
            f.write("def add(a, b):\n    return a + b\n")
        
        # Test import
        response = client.post("/api/repositories/import", json={
            "path": temp_dir,
            "name": "test-calc"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        repo = data["repository"]
        assert repo["name"] == "test-calc"
        assert repo["source_type"] == "local"
        assert repo["status"] == "ready"
        assert repo["stats"]["files_scanned"] >= 1
        
        # Cleanup
        del_resp = client.delete(f"/api/repositories/{repo['id']}")
        assert del_resp.status_code == 200


def test_import_local_invalid_path():
    response = client.post("/api/repositories/import", json={
        "path": "/non/existent/path/for/asterion/test",
        "name": "invalid-path"
    })
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_upload_zip_repository():
    # Build in-memory zip
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("module_a.py", "class Service:\n    def execute(self):\n        return True\n")
        zf.writestr("module_b.py", "from module_a import Service\nservice = Service()\n")
    zip_buffer.seek(0)
    
    response = client.post(
        "/api/repositories/upload",
        files={"file": ("test_project.zip", zip_buffer, "application/zip")},
        data={"name": "test-zip-service"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    repo = data["repository"]
    assert repo["name"] == "test-zip-service"
    assert repo["source_type"] == "zip"
    assert repo["status"] == "ready"
    assert repo["stats"]["files_scanned"] == 2
    assert repo["stats"]["symbols_extracted"] >= 1
    
    # Test repository status endpoint
    status_resp = client.get(f"/api/repositories/{repo['id']}/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["repo_status"] == "ready"
    
    # Test re-indexing endpoint
    index_resp = client.post(f"/api/repositories/{repo['id']}/index")
    assert index_resp.status_code == 200
    assert index_resp.json()["status"] == "success"
    
    # Cleanup
    del_resp = client.delete(f"/api/repositories/{repo['id']}")
    assert del_resp.status_code == 200


def test_upload_zip_rejection_for_non_zip():
    text_buffer = io.BytesIO(b"Hello world not a zip")
    response = client.post(
        "/api/repositories/upload",
        files={"file": ("test.txt", text_buffer, "text/plain")},
        data={"name": "text-file"}
    )
    assert response.status_code == 400
    assert "Invalid or corrupted ZIP" in response.json()["detail"]


def test_zipslip_protection():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        # Malicious ZipSlip path
        zf.writestr("../../evil.txt", "pwned")
    zip_buffer.seek(0)
    
    response = client.post(
        "/api/repositories/upload",
        files={"file": ("malicious.zip", zip_buffer, "application/zip")},
        data={"name": "evil-zip"}
    )
    # Manager should reject unsafe ZipSlip entries
    assert response.status_code == 400
    assert "Path traversal detected" in response.json()["detail"]


def test_delete_demo_repo_protection():
    response = client.delete("/api/repositories/sample_1")
    assert response.status_code == 400
    assert "Cannot delete preloaded demo repository" in response.json()["detail"]


def test_get_nonexistent_repository():
    response = client.get("/api/repositories/non_existent_9999")
    assert response.status_code == 404
