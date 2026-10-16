"""FastAPI router for triggering distributed background jobs via Celery and Redis."""

import os
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
import pandas as pd

from eureka.workers.ingestion_tasks import process_ingestion_chunk

router = APIRouter(prefix="/api/v1/jobs", tags=["Background Jobs"])


def resolve_seed_csv() -> str:
    """Resolve absolute path to english_extreme_scale.csv across directories."""
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../"))
    candidates = [
        os.path.join(root_dir, "backend/seed_data/english_extreme_scale.csv"),
        os.path.join(root_dir, "seed_data/english_extreme_scale.csv"),
        "backend/seed_data/english_extreme_scale.csv",
        "seed_data/english_extreme_scale.csv",
    ]
    for c in candidates:
        if os.path.exists(c):
            return os.path.abspath(c)
    return os.path.join(root_dir, "backend/seed_data/english_extreme_scale.csv")


@router.post("/trigger-ingestion", summary="Trigger Async Batch Ingestion")
def trigger_batch_ingestion(chunk_size: int = 10000, max_chunks: int = None) -> Dict[str, Any]:
    """Reads the synthetic CSV dataset and pushes chunks into the Celery Redis queue.

    The FastAPI response returns immediately, while Celery workers handle database inserts.
    """
    seed_csv = resolve_seed_csv()
    if not os.path.exists(seed_csv):
        raise HTTPException(status_code=404, detail=f"Seed file not found at {seed_csv}")

    try:
        total_chunks = 0
        total_rows_queued = 0

        # Stream the CSV to avoid loading 250k rows into RAM at once
        for chunk in pd.read_csv(seed_csv, chunksize=chunk_size):
            if max_chunks and total_chunks >= max_chunks:
                break

            # Convert datetime columns to string ISO format for JSON serialization
            if "event_timestamp" in chunk.columns:
                chunk["event_timestamp"] = chunk["event_timestamp"].astype(str)

            # Convert pandas DataFrame chunk to a list of dicts for Celery serialization
            records = chunk.to_dict(orient="records")

            # Push to the Redis queue asynchronously
            process_ingestion_chunk.delay(records)
            total_chunks += 1
            total_rows_queued += len(records)

        return {
            "status": "accepted",
            "message": "Batch ingestion triggered successfully.",
            "chunks_queued": total_chunks,
            "rows_queued": total_rows_queued,
            "queue_broker": "Redis",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
