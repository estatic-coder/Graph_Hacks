from fastapi.testclient import TestClient
from app.main import app
from app.config import settings

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["environment"] == settings.environment
    assert "falkordb" in data

def test_config_defaults():
    assert settings.app_name == "ASTERION API"
    assert settings.environment == "development"
