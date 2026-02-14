"""
Latency Benchmark Tests
Validates <5ms P99 latency requirement
"""
import pytest
import requests
import time
import statistics


BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="module")
def setup_test_data():
    """Setup: ensure Redis has test data"""
    # This assumes docker-compose is running
    health = requests.get(f"{BASE_URL}/health")
    assert health.status_code == 200, "Feature server not running"
    
    # Add test features
    test_entity = "test_user_001"
    requests.post(
        f"{BASE_URL}/features/update",
        params={
            "entity_id": test_entity,
            "entity_type": "user",
            "version": "v1"
        },
        json={
            "total_spend": 1500.50,
            "avg_transaction_amount": 75.25,
            "total_transactions": 20,
            "risk_score": 15.5
        }
    )
    
    yield test_entity


def test_single_feature_latency(setup_test_data):
    """Test single entity retrieval latency"""
    
    latencies = []
    n_requests = 100
    
    for _ in range(n_requests):
        start = time.time()
        response = requests.post(
            f"{BASE_URL}/features",
            json={
                "entity_id": setup_test_data,
                "entity_type": "user",
                "version": "v1"
            }
        )
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)
        
        assert response.status_code == 200
    
    # Calculate percentiles
    p50 = statistics.median(latencies)
    p95 = statistics.quantiles(latencies, n=20)[18]  # 95th percentile
    p99 = statistics.quantiles(latencies, n=100)[98]  # 99th percentile
    avg = statistics.mean(latencies)
    
    print(f"\n📊 Single Feature Retrieval Latency ({n_requests} requests):")
    print(f"   P50: {p50:.2f}ms")
    print(f"   P95: {p95:.2f}ms")
    print(f"   P99: {p99:.2f}ms")
    print(f"   Avg: {avg:.2f}ms")
    
    # Assert P99 < 5ms (our target)
    assert p99 < 5.0, f"P99 latency {p99:.2f}ms exceeds 5ms target"


def test_batch_feature_latency(setup_test_data):
    """Test batch retrieval efficiency"""
    
    # Create multiple test entities
    test_entities = [f"test_user_{i:03d}" for i in range(10)]
    
    for entity in test_entities:
        requests.post(
            f"{BASE_URL}/features/update",
            params={"entity_id": entity, "entity_type": "user"},
            json={"total_spend": 1000.0}
        )
    
    latencies_per_entity = []
    n_requests = 50
    
    for _ in range(n_requests):
        start = time.time()
        response = requests.post(
            f"{BASE_URL}/features/batch",
            json={
                "entity_ids": test_entities,
                "entity_type": "user",
                "version": "v1"
            }
        )
        total_latency_ms = (time.time() - start) * 1000
        
        assert response.status_code == 200
        
        data = response.json()
        latency_per_entity = total_latency_ms / len(test_entities)
        latencies_per_entity.append(latency_per_entity)
    
    p99 = statistics.quantiles(latencies_per_entity, n=100)[98]
    avg = statistics.mean(latencies_per_entity)
    
    print(f"\n📊 Batch Retrieval Latency (10 entities, {n_requests} requests):")
    print(f"   P99 per entity: {p99:.2f}ms")
    print(f"   Avg per entity: {avg:.2f}ms")
    print(f"   Throughput: ~{1000/avg:.0f} entities/sec")
    
    # Batch should be more efficient
    assert p99 < 5.0, f"Batch P99 latency {p99:.2f}ms exceeds 5ms target"


def test_cache_hit_performance(setup_test_data):
    """Test that cache hits are fast"""
    
    # First request (cache miss possible)
    requests.post(
        f"{BASE_URL}/features",
        json={
            "entity_id": setup_test_data,
            "entity_type": "user"
        }
    )
    
    # Subsequent requests (cache hits)
    latencies = []
    for _ in range(100):
        start = time.time()
        requests.post(
            f"{BASE_URL}/features",
            json={
                "entity_id": setup_test_data,
                "entity_type": "user"
            }
        )
        latency_ms = (time.time() - start) * 1000
        latencies.append(latency_ms)
    
    avg_cache_hit_latency = statistics.mean(latencies)
    
    print(f"\n📊 Cache Hit Latency:")
    print(f"   Average: {avg_cache_hit_latency:.2f}ms")
    
    # Cache hits should be very fast
    assert avg_cache_hit_latency < 10.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
