"""
Sync Offline Features to Online Store
Pushes batch-computed features from Parquet to Redis
"""
import pandas as pd
import redis
import json
import logging
from pathlib import Path
from typing import Optional
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FeatureSync:
    """Syncs offline features to online Redis store"""
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=0,
            decode_responses=True
        )
        logger.info(f"✅ Connected to Redis at {redis_host}:{redis_port}")
    
    def sync_features_from_parquet(
        self,
        parquet_path: Path,
        entity_type: str,
        entity_id_column: str = "user_id",
        version: str = "latest",
        ttl: Optional[int] = None,
        batch_size: int = 1000
    ) -> dict:
        """
        Sync features from Parquet file to Redis
        
        Args:
            parquet_path: Path to Parquet file
            entity_type: Type of entity (e.g., 'user', 'transaction')
            entity_id_column: Column name containing entity IDs
            version: Feature version
            ttl: Time-to-live in seconds (None = no expiration)
            batch_size: Number of records to process in each batch
        
        Returns:
            dict with sync statistics
        """
        logger.info(f"📥 Loading features from {parquet_path}...")
        df = pd.read_parquet(parquet_path)
        
        total_records = len(df)
        logger.info(f"📊 Processing {total_records} records...")
        
        # Verify entity_id column exists
        if entity_id_column not in df.columns:
            raise ValueError(f"Column '{entity_id_column}' not found in DataFrame")
        
        # Drop metadata columns
        metadata_cols = [col for col in df.columns if col.startswith('_')]
        feature_columns = [col for col in df.columns if col not in metadata_cols and col != entity_id_column]
        
        # Process in batches
        success_count = 0
        error_count = 0
        start_time = time.time()
        
        pipe = self.redis_client.pipeline()
        
        for idx, row in df.iterrows():
            entity_id = str(row[entity_id_column])
            
            # Extract features (exclude entity_id and metadata)
            features = row[feature_columns].to_dict()
            
            # Convert numpy types to Python types
            features = {
                k: (v.item() if hasattr(v, 'item') else v)
                for k, v in features.items()
            }
            
            # Convert NaN to None
            features = {k: (None if pd.isna(v) else v) for k, v in features.items()}
            
            # Construct Redis key
            key = f"{entity_type}:{version}:{entity_id}"
            
            try:
                value = json.dumps(features)
                
                if ttl:
                    pipe.setex(key, ttl, value)
                else:
                    pipe.set(key, value)
                
                success_count += 1
                
                # Execute batch
                if (idx + 1) % batch_size == 0:
                    pipe.execute()
                    pipe = self.redis_client.pipeline()
                    logger.info(f"  Processed {idx + 1}/{total_records} records...")
                
            except Exception as e:
                logger.error(f"Error syncing entity {entity_id}: {e}")
                error_count += 1
        
        # Execute remaining
        if success_count % batch_size != 0:
            pipe.execute()
        
        elapsed = time.time() - start_time
        
        stats = {
            "total_records": total_records,
            "success": success_count,
            "errors": error_count,
            "elapsed_seconds": round(elapsed, 2),
            "records_per_second": round(total_records / elapsed, 2),
            "entity_type": entity_type,
            "version": version,
            "feature_count": len(feature_columns)
        }
        
        logger.info(f"✅ Sync complete!")
        logger.info(f"   Success: {success_count}/{total_records}")
        logger.info(f"   Errors: {error_count}")
        logger.info(f"   Speed: {stats['records_per_second']} records/sec")
        
        return stats
    
    def verify_sync(
        self,
        entity_ids: list,
        entity_type: str,
        version: str = "latest"
    ) -> dict:
        """Verify that entities were synced correctly"""
        
        found = 0
        not_found = 0
        
        for entity_id in entity_ids:
            key = f"{entity_type}:{version}:{entity_id}"
            exists = self.redis_client.exists(key)
            
            if exists:
                found += 1
            else:
                not_found += 1
        
        return {
            "checked": len(entity_ids),
            "found": found,
            "not_found": not_found,
            "success_rate": round(found / len(entity_ids) * 100, 2)
        }


if __name__ == "__main__":
    import sys
    
    # Example usage
    syncer = FeatureSync(redis_host="localhost", redis_port=6379)
    
    # Find latest parquet file
    data_dir = Path("./data/offline-features")
    
    if not data_dir.exists():
        print("❌ No offline features found. Run compute_features.py first.")
        sys.exit(1)
    
    parquet_files = list(data_dir.glob("user_*.parquet"))
    
    if not parquet_files:
        print("❌ No parquet files found")
        sys.exit(1)
    
    # Use most recent file
    latest_file = max(parquet_files, key=lambda p: p.stat().st_mtime)
    
    print(f"📥 Syncing features from {latest_file.name}...")
    
    # Sync to Redis
    stats = syncer.sync_features_from_parquet(
        parquet_path=latest_file,
        entity_type="user",
        entity_id_column="user_id",
        version="v1",
        ttl=86400  # 24 hours
    )
    
    print("\n📊 Sync Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    # Verify a sample
    print("\n🔍 Verifying sample...")
    df = pd.read_parquet(latest_file)
    sample_ids = df['user_id'].sample(min(10, len(df))).tolist()
    
    verification = syncer.verify_sync(
        entity_ids=sample_ids,
        entity_type="user",
        version="v1"
    )
    
    print(f"  Verified {verification['checked']} entities")
    print(f"  Success rate: {verification['success_rate']}%")
