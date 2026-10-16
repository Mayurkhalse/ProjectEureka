"""Asynchronous distributed ingestion tasks for Project EUREKA."""

import os
from typing import Any, Dict, List, Optional
from celery.utils.log import get_task_logger
import pandas as pd
from sqlalchemy import create_engine

from eureka.core.celery_app import celery_app
from eureka.db.models import Base, MediaEvent
from eureka.db.seeder import DATABASE_URL, normalize_db_url, seed_database

logger = get_task_logger(__name__)


@celery_app.task(bind=True, name="eureka.workers.process_ingestion_chunk")
def process_ingestion_chunk(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ingest a chunk of synthetic records into the database (PostgreSQL/SQLite).

    Args:
        records: List of record dictionaries to be written to media_events.
    """
    logger.info("Processing ingestion chunk of %s records...", len(records))
    try:
        engine = create_engine(normalize_db_url(DATABASE_URL))
        Base.metadata.create_all(bind=engine)

        df = pd.DataFrame(records)
        df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
        valid_cols = [c.name for c in MediaEvent.__table__.columns]
        filtered_cols = [col for col in valid_cols if col in df.columns]

        df[filtered_cols].to_sql("media_events", engine, if_exists="append", index=False)
        logger.info("Committed chunk of %s records to database.", len(df))
        return {
            "status": "success",
            "task_id": self.request.id,
            "rows_inserted": len(df),
        }
    except Exception as exc:
        logger.error("Chunk ingestion failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=5, max_retries=3)


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
