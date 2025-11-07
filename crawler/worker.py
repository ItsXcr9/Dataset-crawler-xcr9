import json
import os
import time

import structlog

from common.job_utils import get_job, redis_client, update_job_status
from crawler.crawler import run_crawler

logger = structlog.get_logger()

QUEUE_NAME = os.getenv("CRAWLER_QUEUE", "crawl_queue")
IDLE_SLEEP = float(os.getenv("CRAWLER_IDLE_SLEEP", "1.0"))


def handle_job(job_id: str, job: dict) -> None:
    params = job.get("params", {})
    start_url = params.get("start_url")
    max_depth = int(params.get("max_depth", 3))
    output_dir = params.get("output_dir", "dataset/raw")

    if not start_url:
        update_job_status(job_id, "failed", 0.0, "Missing start_url parameter")
        return

    update_job_status(job_id, "running", 0.1, "Crawler started")
    try:
        run_crawler(start_url=start_url, max_depth=max_depth, output_dir=output_dir)
        update_job_status(job_id, "completed", 1.0, "Crawler finished successfully")
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Crawler job failed", job_id=job_id, error=str(exc))
        update_job_status(job_id, "failed", 0.0, f"Crawler failed: {exc}")


def main() -> None:
    logger.info("Crawler worker started", queue=QUEUE_NAME)
    while True:
        try:
            job_entry = redis_client.blpop(QUEUE_NAME, timeout=5)
            if not job_entry:
                time.sleep(IDLE_SLEEP)
                continue

            _, job_id_bytes = job_entry
            job_id = job_id_bytes.decode()
            job = get_job(job_id)
            if not job:
                logger.warning("Received job id with no payload", job_id=job_id)
                continue

            handle_job(job_id, job)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Crawler worker loop error", error=str(exc))
            time.sleep(5)


if __name__ == "__main__":
    main()
