#!/usr/bin/env python3
"""
FastAPI service for dataset crawler management and monitoring.
"""

import os
import json
from typing import List, Dict, Optional, Any
from datetime import datetime
from pathlib import Path
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import redis
import psycopg2
from psycopg2.extras import RealDictCursor
import structlog
from pydantic import BaseModel

from dataset_manager import DatasetManager
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

logger = structlog.get_logger()

app = FastAPI(
    title="Dataset Crawler API",
    description="API for managing web crawling and dataset creation",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
dataset_manager = DatasetManager()

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        database=os.getenv("POSTGRES_DB", "crawldb"),
        user=os.getenv("POSTGRES_USER", "crawler"),
        password=os.getenv("POSTGRES_PASSWORD", "crawler123"),
        cursor_factory=RealDictCursor
    )

# Redis connection
redis_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

REQUEST_COUNTER = Counter(
    'dataset_api_requests_total',
    'Total API requests handled by the API',
    ['method', 'endpoint', 'status_code']
)
REQUEST_LATENCY = Histogram(
    'dataset_api_request_latency_seconds',
    'Latency of API requests in seconds',
    ['endpoint']
)

@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    start_time = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        endpoint = request.url.path
        elapsed = time.perf_counter() - start_time
        REQUEST_COUNTER.labels(request.method, endpoint, str(status_code)).inc()
        REQUEST_LATENCY.labels(endpoint).observe(elapsed)

# Pydantic models
class CrawlRequest(BaseModel):
    start_url: str
    max_depth: int = 3
    allowed_domains: Optional[List[str]] = None

class ProcessRequest(BaseModel):
    raw_dir: str = "dataset/raw"
    output_dir: str = "dataset"

class TokenizeRequest(BaseModel):
    cleaned_dir: str = "dataset/cleaned"
    shards_dir: str = "dataset/shards"
    model_name: str = "microsoft/DialoGPT-medium"
    max_length: int = 2048
    val_split: float = 0.05

class JobStatus(BaseModel):
    job_id: str
    status: str
    progress: float
    message: str
    created_at: datetime
    updated_at: datetime

@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "Dataset Crawler API", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check database
        conn = get_db_connection()
        conn.close()

        # Check Redis
        redis_client.ping()

        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

@app.post("/crawl", response_model=Dict[str, Any])
async def start_crawl(request: CrawlRequest):
    """Start a web crawling job"""
    job_id = f"crawl_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    # Store job in Redis
    job_data = {
        "job_id": job_id,
        "type": "crawl",
        "status": "queued",
        "progress": 0.0,
        "message": "Job queued",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "params": request.dict()
    }

    redis_client.set(f"job:{job_id}", json.dumps(job_data))

    # Add to job queue
    redis_client.rpush("crawl_queue", job_id)


    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Crawl job started"
    }

@app.post("/process", response_model=Dict[str, Any])
async def start_processing(request: ProcessRequest):
    """Start data processing job"""
    job_id = f"process_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    job_data = {
        "job_id": job_id,
        "type": "process",
        "status": "queued",
        "progress": 0.0,
        "message": "Job queued",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "params": request.dict()
    }

    redis_client.set(f"job:{job_id}", json.dumps(job_data))
    redis_client.rpush("process_queue", job_id)


    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Processing job started"
    }

@app.post("/tokenize", response_model=Dict[str, Any])
async def start_tokenization(request: TokenizeRequest):
    """Start tokenization and sharding job"""
    job_id = f"tokenize_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

    job_data = {
        "job_id": job_id,
        "type": "tokenize",
        "status": "queued",
        "progress": 0.0,
        "message": "Job queued",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "params": request.dict()
    }

    redis_client.set(f"job:{job_id}", json.dumps(job_data))
    redis_client.rpush("tokenize_queue", job_id)


    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Tokenization job started"
    }

@app.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job_status(job_id: str):
    """Get job status"""
    job_data = redis_client.get(f"job:{job_id}")
    if not job_data:
        raise HTTPException(status_code=404, detail="Job not found")

    job = json.loads(job_data)
    return JobStatus(**job)

@app.get("/jobs", response_model=List[JobStatus])
async def list_jobs():
    """List all jobs"""
    jobs = []
    for key in redis_client.scan_iter("job:*"):
        job_data = redis_client.get(key)
        if job_data:
            jobs.append(JobStatus(**json.loads(job_data)))

    # Sort by creation time
    jobs.sort(key=lambda x: x.created_at, reverse=True)
    return jobs

@app.get("/dataset/summary")
async def get_dataset_summary():
    """Get dataset summary"""
    try:
        summary = dataset_manager.get_dataset_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dataset/versions")
async def list_dataset_versions():
    """List dataset versions"""
    try:
        versions = dataset_manager.list_versions()
        return {"versions": versions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dataset/version/{version}")
async def get_version_info(version: str):
    """Get version information"""
    try:
        version_info = dataset_manager.get_version_info(version)
        return version_info.__dict__
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/dataset/version")
async def create_dataset_version(description: str):
    """Create a new dataset version"""
    try:
        # Mock statistics (would be calculated from actual data)
        stats = {"total_docs": 1000, "total_tokens": 500000}
        quality = {"avg_quality": 0.85}
        provenance = {"pipeline": "v1.0"}

        version = dataset_manager.create_version(description, stats, quality, provenance)

        return {"version": version, "message": "Version created successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics")
async def metrics():
    """Expose Prometheus metrics for this API"""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
