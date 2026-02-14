"""
Real-Time Feature Store Server
Serves features with sub-5ms latency from Redis
"""
import time
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
import redis
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Prometheus metrics
FEATURE_REQUESTS = Counter(
    'feature_requests_total',
    'Total feature requests',
    ['entity_type', 'status']
)
FEATURE_LATENCY = Histogram(
    'feature_latency_seconds',
    'Feature retrieval latency',
    ['entity_type'],
    buckets=[0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1]  # Focus on ms-level
)
CACHE_HITS = Counter('cache_hits_total', 'Cache hits', ['entity_type'])
CACHE_MISSES = Counter('cache_misses_total', 'Cache misses', ['entity_type'])

# Request/Response models
class FeatureRequest(BaseModel):
    """Request schema for feature retrieval"""
    entity_id: str = Field(..., description="Entity ID (e.g., user_id, transaction_id)")
    entity_type: str = Field(..., description="Entity type (e.g., user, transaction)")
    feature_names: Optional[List[str]] = Field(None, description="Specific features to retrieve (None = all)")
    version: str = Field(default="latest", description="Feature version")

    class Config:
        json_schema_extra = {
            "example": {
                "entity_id": "user_12345",
                "entity_type": "user",
                "feature_names": ["age", "country", "total_purchases"],
                "version": "v1"
            }
        }


class FeatureResponse(BaseModel):
    """Response schema for features"""
    entity_id: str
    entity_type: str
    features: Dict[str, Any]
    version: str
    retrieved_at: str
    latency_ms: float


class BatchFeatureRequest(BaseModel):
    """Batch feature retrieval"""
    entity_ids: List[str] = Field(..., max_length=100)
    entity_type: str
    feature_names: Optional[List[str]] = None
    version: str = Field(default="latest")


# Redis connection
class FeatureStore:
    """Interface to Redis feature storage"""
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379):
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"✅ Connected to Redis at {redis_host}:{redis_port}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Redis: {e}")
            raise
    
    def get_features(
        self,
        entity_id: str,
        entity_type: str,
        feature_names: Optional[List[str]] = None,
        version: str = "latest"
    ) -> Dict[str, Any]:
        """Retrieve features for an entity"""
        
        # Construct Redis key
        key = f"{entity_type}:{version}:{entity_id}"
        
        try:
            # Get from Redis
            feature_data = self.redis_client.get(key)
            
            if feature_data is None:
                CACHE_MISSES.labels(entity_type=entity_type).inc()
                return {}
            
            CACHE_HITS.labels(entity_type=entity_type).inc()
            
            # Parse JSON
            all_features = json.loads(feature_data)
            
            # Filter requested features if specified
            if feature_names:
                return {k: v for k, v in all_features.items() if k in feature_names}
            
            return all_features
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON for key {key}")
            return {}
        except Exception as e:
            logger.error(f"Error retrieving features for {key}: {e}")
            return {}
    
    def batch_get_features(
        self,
        entity_ids: List[str],
        entity_type: str,
        feature_names: Optional[List[str]] = None,
        version: str = "latest"
    ) -> Dict[str, Dict[str, Any]]:
        """Batch retrieve features"""
        
        # Use Redis pipeline for efficiency
        pipe = self.redis_client.pipeline()
        
        keys = [f"{entity_type}:{version}:{eid}" for eid in entity_ids]
        for key in keys:
            pipe.get(key)
        
        results = pipe.execute()
        
        # Parse results
        features_map = {}
        for entity_id, result in zip(entity_ids, results):
            if result:
                try:
                    all_features = json.loads(result)
                    if feature_names:
                        features_map[entity_id] = {
                            k: v for k, v in all_features.items() if k in feature_names
                        }
                    else:
                        features_map[entity_id] = all_features
                    CACHE_HITS.labels(entity_type=entity_type).inc()
                except json.JSONDecodeError:
                    features_map[entity_id] = {}
            else:
                features_map[entity_id] = {}
                CACHE_MISSES.labels(entity_type=entity_type).inc()
        
        return features_map
    
    def set_features(
        self,
        entity_id: str,
        entity_type: str,
        features: Dict[str, Any],
        version: str = "latest",
        ttl: Optional[int] = None
    ) -> bool:
        """Store features for an entity"""
        
        key = f"{entity_type}:{version}:{entity_id}"
        
        try:
            value = json.dumps(features)
            
            if ttl:
                self.redis_client.setex(key, ttl, value)
            else:
                self.redis_client.set(key, value)
            
            return True
        except Exception as e:
            logger.error(f"Error storing features for {key}: {e}")
            return False


# FastAPI app
app = FastAPI(
    title="Real-Time Feature Store",
    description="Low-latency feature serving with Redis backend",
    version="1.0.0"
)

# Global feature store
feature_store: Optional[FeatureStore] = None


@app.on_event("startup")
async def startup_event():
    """Initialize feature store on startup"""
    global feature_store
    try:
        import os
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        
        feature_store = FeatureStore(redis_host=redis_host, redis_port=redis_port)
        logger.info("🚀 Feature Store startup complete")
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all requests with timing"""
    start_time = time.time()
    response = await call_next(request)
    duration = (time.time() - start_time) * 1000
    logger.info(
        f"{request.method} {request.url.path} - "
        f"Status: {response.status_code} - "
        f"Duration: {duration:.2f}ms"
    )
    return response


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        feature_store.redis_client.ping()
        return {
            "status": "healthy",
            "redis_connected": True,
            "timestamp": datetime.utcnow().isoformat()
        }
    except:
        raise HTTPException(status_code=503, detail="Redis not available")


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )


@app.post("/features", response_model=FeatureResponse)
async def get_features(request: FeatureRequest):
    """
    Retrieve features for a single entity
    
    Target: <5ms P99 latency
    """
    if feature_store is None:
        raise HTTPException(status_code=503, detail="Feature store not initialized")
    
    start_time = time.time()
    
    try:
        with FEATURE_LATENCY.labels(entity_type=request.entity_type).time():
            features = feature_store.get_features(
                entity_id=request.entity_id,
                entity_type=request.entity_type,
                feature_names=request.feature_names,
                version=request.version
            )
        
        latency_ms = (time.time() - start_time) * 1000
        
        if not features:
            FEATURE_REQUESTS.labels(
                entity_type=request.entity_type,
                status="not_found"
            ).inc()
            raise HTTPException(
                status_code=404,
                detail=f"Features not found for {request.entity_type}:{request.entity_id}"
            )
        
        FEATURE_REQUESTS.labels(
            entity_type=request.entity_type,
            status="success"
        ).inc()
        
        return FeatureResponse(
            entity_id=request.entity_id,
            entity_type=request.entity_type,
            features=features,
            version=request.version,
            retrieved_at=datetime.utcnow().isoformat(),
            latency_ms=latency_ms
        )
        
    except HTTPException:
        raise
    except Exception as e:
        FEATURE_REQUESTS.labels(
            entity_type=request.entity_type,
            status="error"
        ).inc()
        logger.error(f"Error retrieving features: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/features/batch")
async def get_features_batch(request: BatchFeatureRequest):
    """
    Batch retrieve features for multiple entities
    
    More efficient than multiple single requests
    """
    if feature_store is None:
        raise HTTPException(status_code=503, detail="Feature store not initialized")
    
    start_time = time.time()
    
    try:
        features_map = feature_store.batch_get_features(
            entity_ids=request.entity_ids,
            entity_type=request.entity_type,
            feature_names=request.feature_names,
            version=request.version
        )
        
        latency_ms = (time.time() - start_time) * 1000
        
        return {
            "entity_type": request.entity_type,
            "features": features_map,
            "version": request.version,
            "count": len(features_map),
            "retrieved_at": datetime.utcnow().isoformat(),
            "latency_ms": latency_ms,
            "avg_latency_per_entity_ms": latency_ms / len(request.entity_ids) if request.entity_ids else 0
        }
        
    except Exception as e:
        logger.error(f"Error in batch retrieval: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/features/update")
async def update_features(
    entity_id: str,
    entity_type: str,
    features: Dict[str, Any],
    version: str = "latest",
    ttl: Optional[int] = None
):
    """
    Update features for an entity
    
    Used by offline batch jobs to sync to online store
    """
    if feature_store is None:
        raise HTTPException(status_code=503, detail="Feature store not initialized")
    
    success = feature_store.set_features(
        entity_id=entity_id,
        entity_type=entity_type,
        features=features,
        version=version,
        ttl=ttl
    )
    
    if success:
        return {
            "status": "success",
            "entity_id": entity_id,
            "entity_type": entity_type,
            "version": version
        }
    else:
        raise HTTPException(status_code=500, detail="Failed to update features")


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "service": "Real-Time Feature Store",
        "version": "1.0.0",
        "description": "Low-latency feature serving with Redis backend",
        "endpoints": {
            "get_features": "POST /features",
            "batch_get": "POST /features/batch",
            "update": "POST /features/update",
            "health": "GET /health",
            "metrics": "GET /metrics",
            "docs": "GET /docs"
        },
        "performance_target": "<5ms P99 latency"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
