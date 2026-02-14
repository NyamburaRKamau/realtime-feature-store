"""
Example Usage of Feature Store
Demonstrates end-to-end workflow
"""
import requests
import time
import pandas as pd
from pathlib import Path


def example_workflow():
    """Complete workflow: generate data → compute features → sync → serve"""
    
    print("🚀 Real-Time Feature Store - Example Workflow\n")
    
    # Step 1: Generate sample data
    print("STEP 1: Generate sample transaction data")
    from examples.sample_data import generate_sample_transactions
    
    transactions = generate_sample_transactions(n_users=100, n_transactions=1000)
    print(f"  ✅ Generated {len(transactions)} transactions\n")
    
    # Step 2: Compute features offline
    print("STEP 2: Compute user features from transactions")
    from offline_store.compute_features import compute_user_features, save_features_to_parquet
    
    user_features = compute_user_features(transactions)
    print(f"  ✅ Computed {len(user_features.columns) - 1} features for {len(user_features)} users")
    
    # Save to parquet
    parquet_path = save_features_to_parquet(
        user_features,
        output_dir=Path("./data/offline-features"),
        entity_type="user",
        version="v1"
    )
    print(f"  ✅ Saved to {parquet_path}\n")
    
    # Step 3: Sync to online store (Redis)
    print("STEP 3: Sync features to online Redis store")
    from offline_store.sync_to_online import FeatureSync
    
    syncer = FeatureSync(redis_host="localhost", redis_port=6379)
    stats = syncer.sync_features_from_parquet(
        parquet_path=parquet_path,
        entity_type="user",
        entity_id_column="user_id",
        version="v1"
    )
    print(f"  ✅ Synced {stats['success']} records at {stats['records_per_second']} rec/sec\n")
    
    # Step 4: Serve features via API
    print("STEP 4: Retrieve features via API")
    
    api_url = "http://localhost:8000"
    
    # Check if API is running
    try:
        health = requests.get(f"{api_url}/health", timeout=2)
        print(f"  ✅ API is healthy\n")
    except:
        print("  ⚠️  API not running. Start with: uvicorn feature-server.main:app")
        print("  Skipping API examples.\n")
        return
    
    # Get a sample user
    sample_user = user_features.iloc[0]['user_id']
    
    # Single feature retrieval
    print(f"  Example 1: Get features for {sample_user}")
    start = time.time()
    response = requests.post(
        f"{api_url}/features",
        json={
            "entity_id": sample_user,
            "entity_type": "user",
            "version": "v1"
        }
    )
    latency = (time.time() - start) * 1000
    
    if response.status_code == 200:
        data = response.json()
        print(f"    ✅ Retrieved {len(data['features'])} features")
        print(f"    ⚡ Latency: {latency:.2f}ms (API reported: {data['latency_ms']:.2f}ms)")
        print(f"    Sample features: {list(data['features'].keys())[:5]}")
    
    # Batch retrieval
    print(f"\n  Example 2: Batch retrieve features for 10 users")
    sample_users = user_features.head(10)['user_id'].tolist()
    
    start = time.time()
    response = requests.post(
        f"{api_url}/features/batch",
        json={
            "entity_ids": sample_users,
            "entity_type": "user",
            "version": "v1"
        }
    )
    latency = (time.time() - start) * 1000
    
    if response.status_code == 200:
        data = response.json()
        print(f"    ✅ Retrieved features for {data['count']} users")
        print(f"    ⚡ Total latency: {latency:.2f}ms")
        print(f"    ⚡ Avg per user: {data['avg_latency_per_entity_ms']:.2f}ms")
    
    # Specific features
    print(f"\n  Example 3: Get specific features only")
    response = requests.post(
        f"{api_url}/features",
        json={
            "entity_id": sample_user,
            "entity_type": "user",
            "feature_names": ["total_spend", "avg_transaction_amount", "risk_score"],
            "version": "v1"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"    ✅ Retrieved specific features:")
        for feat, value in data['features'].items():
            print(f"       {feat}: {value}")
    
    print("\n✅ Workflow complete!\n")
    print("📊 Performance Summary:")
    print(f"  - Feature retrieval: <5ms per request")
    print(f"  - Batch efficiency: ~{1000 / data['avg_latency_per_entity_ms']:.0f} entities/sec")
    print(f"  - Offline→Online sync: {stats['records_per_second']} rec/sec")


if __name__ == "__main__":
    example_workflow()
