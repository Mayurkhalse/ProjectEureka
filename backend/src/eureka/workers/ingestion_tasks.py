"""Asynchronous distributed ingestion tasks for Project EUREKA."""

import os
from typing import Any, Dict, Optional
from celery.utils.log import get_task_logger

from eureka.core.celery_app import celery_app
from eureka.db.seeder import seed_database

logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="eureka.workers.ingest_synthetic_dataset_task")
def ingest_synthetic_dataset_task(
    self,
    limit_rows: Optional[int] = None,
    chunk_size: int = 10000,
) -> Dict[str, Any]:
    """Asynchronously ingest extreme-scale dataset into the database in chunks.

    Prevents blocking the main FastAPI event loop.
    """
    logger.info("Starting asynchronous bulk dataset ingestion (limit=%s, chunk_size=%s)...", limit_rows, chunk_size)
    try:
        total_inserted = seed_database(limit_rows=limit_rows, chunk_size=chunk_size)
        logger.info("Successfully ingested %s records asynchronously.", total_inserted)
        return {
            "status": "success",
            "task_id": self.request.id,
            "rows_ingested": total_inserted,
        }
    except Exception as exc:
        logger.error("Asynchronous ingestion failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=5, max_retries=3)
