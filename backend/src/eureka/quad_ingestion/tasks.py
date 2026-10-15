"""QUAD Ingestion Celery tasks re-export from eureka.tasks.quad_tasks."""

from eureka.tasks.quad_tasks import (
    ingest_csv_task,
    ingest_source_task,
    scrape_url_task,
)

__all__ = [
    "ingest_source_task",
    "ingest_csv_task",
    "scrape_url_task",
]
