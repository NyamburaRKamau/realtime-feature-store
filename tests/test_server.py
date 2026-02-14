"""
API Integration Tests
Tests feature server endpoints
"""
import pytest
import requests


BASE_URL = "http://localhost:8000"


def test_health_check():
    """Test health endpoint"""
    response = requests.get(f"{BASE_URL}/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["redis_connected"] is True


def test_get_features_success():
    """Test successful feature retrieval"""
    # First, add a test entity
    entity_id = "test_user_api"
    requests.post(
        f"{BASE_URL}/features/update",
        params={
            "entity_id": entity_id,
            "entity_type": "user"
        },
        json={
            "feature1": 100.0,
            "feature2": "test_value"
        }
    )
    
    # Retrieve features
    response = requests.post(
        f"{BASE_URL}/features",
        json={
            "entity_id": entity_id,
            "entity_type": "user"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["entity_id"] == entity_id
    assert data["entity_type"] == "user"
    assert "features" in data
    assert data["features"]["feature1"] == 100.0


def test_get_features_not_found():
    """Test feature retrieval for non-existent entity"""
    response = requests.post(
        f"{BASE_URL}/features",
        json={
            "entity_id": "nonexistent_user",
            "entity_type": "user"
        }
    )
    
    assert response.status_code == 404


def test_batch_feature_retrieval():
    """Test batch feature retrieval"""
    # Add multiple test entities
    entities = [f"batch_user_{i}" for i in range(5)]
    for entity in entities:
        requests.post(
            f"{BASE_URL}/features/update",
            params={"entity_id": entity, "entity_type": "user"},
            json={"value": i * 10}
        )
    
    # Batch retrieve
    response = requests.post(
        f"{BASE_URL}/features/batch",
        json={
            "entity_ids": entities,
            "entity_type": "user"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == len(entities)
    assert len(data["features"]) == len(entities)


def test_specific_features_only():
    """Test retrieving specific features"""
    entity_id = "test_specific_features"
    
    # Add entity with multiple features
    requests.post(
        f"{BASE_URL}/features/update",
        params={"entity_id": entity_id, "entity_type": "user"},
        json={
            "feature_a": 1.0,
            "feature_b": 2.0,
            "feature_c": 3.0
        }
    )
    
    # Request only specific features
    response = requests.post(
        f"{BASE_URL}/features",
        json={
            "entity_id": entity_id,
            "entity_type": "user",
            "feature_names": ["feature_a", "feature_c"]
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    features = data["features"]
    
    assert "feature_a" in features
    assert "feature_c" in features
    assert "feature_b" not in features


def test_metrics_endpoint():
    """Test Prometheus metrics endpoint"""
    response = requests.get(f"{BASE_URL}/metrics")
    assert response.status_code == 200
    assert "feature_requests_total" in response.text
    assert "feature_latency_seconds" in response.text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])