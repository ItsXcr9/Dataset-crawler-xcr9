import json
import os
import time
from typing import Dict

import structlog

from common.job_utils import get_job, redis_client, update_job_status
from processor.data_processor import DataProcessor
from processor.tokenizer_sharder import TokenizerSharder

logger = structlog.get_logger()

PROCESS_QUEUE = os.getenv("PROCESS_QUEUE", "process_queue")
TOKENIZE_QUEUE = os.getenv("TOKENIZE_QUEUE", "tokenize_queue")
IDLE_SLEEP = float(os.getenv("PROCESSOR_IDLE_SLEEP", "1.0"))


def handle_process_job(job_id: str, job: Dict) -> None:
    params = job.get("params", {})
    raw_dir = params.get("raw_dir", "dataset/raw")
    output_dir = params.get("output_dir", "dataset")

    update_job_status(job_id, "running", 0.1, "Processing started")
    try:
        processor = DataProcessor()
        stats = processor.process_dataset(raw_dir, output_dir)
        message = f"Processing completed: {stats['processed_docs']} docs processed"
        update_job_status(job_id, "completed", 1.0, message)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Processing job failed", job_id=job_id, error=str(exc))
        update_job_status(job_id, "failed", 0.0, f"Processing failed: {exc}")


def handle_tokenize_job(job_id: str, job: Dict) -> None:
    params = job.get("params", {})
    cleaned_dir = params.get("cleaned_dir", "dataset/cleaned")
    shards_dir = params.get("shards_dir", "dataset/shards")
    model_name = params.get("model_name", "microsoft/DialoGPT-medium")
    max_length = int(params.get("max_length", 2048))
    val_split = float(params.get("val_split", 0.05))

    update_job_status(job_id, "running", 0.1, "Tokenization started")
    try:
        sharder = TokenizerSharder(model_name=model_name, max_length=max_length)
        stats = sharder.process_dataset(cleaned_dir, shards_dir, val_split)
        message = (
            f"Tokenization completed: {stats['train_shards']} train shards, "
            f"{stats['total_tokens']} tokens"
        )
        update_job_status(job_id, "completed", 1.0, message)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("Tokenization job failed", job_id=job_id, error=str(exc))
        update_job_status(job_id, "failed", 0.0, f"Tokenization failed: {exc}")


def main() -> None:
    logger.info(
        "Processor worker started",
        process_queue=PROCESS_QUEUE,
        tokenize_queue=TOKENIZE_QUEUE,
    )
    queues = [PROCESS_QUEUE, TOKENIZE_QUEUE]
    while True:
        try:
            item = redis_client.blpop(queues, timeout=5)
            if not item:
                time.sleep(IDLE_SLEEP)
                continue

            queue_name, job_id_bytes = item
            job_id = job_id_bytes.decode()
            job = get_job(job_id)
            if not job:
                logger.warning("Received job id with no payload", job_id=job_id)
                continue

            queue_decoded = queue_name.decode()
            if queue_decoded == PROCESS_QUEUE:
                handle_process_job(job_id, job)
            elif queue_decoded == TOKENIZE_QUEUE:
                handle_tokenize_job(job_id, job)
            else:
                logger.warning("Unknown queue received", queue=queue_decoded)
        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Processor worker loop error", error=str(exc))
            time.sleep(5)


if __name__ == "__main__":
    main()
