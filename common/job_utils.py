import json
import os
from datetime import datetime
from typing import Optional

import redis
import structlog

logger = structlog.get_logger()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
redis_client = redis.Redis.from_url(REDIS_URL)


def get_job(job_id: str) -> Optional[dict]:
    """Fetch a job definition from Redis."""
    data = redis_client.get(f"job:{job_id}")
    if not data:
        logger.warning("Job data missing", job_id=job_id)
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        logger.error("Invalid job payload", job_id=job_id)
        return None


def update_job_payload(job_id: str, payload: dict) -> None:
    redis_client.set(f"job:{job_id}", json.dumps(payload))


def update_job_status(job_id: str, status: str, progress: float, message: str) -> bool:
    """Update job metadata in Redis."""
    job = get_job(job_id)
    if not job:
        return False

    job.update(
        {
            "status": status,
            "progress": progress,
            "message": message,
            "updated_at": datetime.utcnow().isoformat(),
        }
    )
    update_job_payload(job_id, job)
    return True
