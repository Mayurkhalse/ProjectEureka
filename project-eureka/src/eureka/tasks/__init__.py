"""Project EUREKA distributed Celery tasks export."""

from eureka.tasks.irf_tasks import normalize_and_bind_task
from eureka.tasks.outbox_tasks import (
    BatchNeo4jOutboxProjector,
    poll_outbox_events_task,
    process_pending_outbox_unwind_batch,
)
from eureka.tasks.quad_tasks import ingest_csv_task, ingest_source_task, scrape_url_task
from eureka.tasks.scoring_tasks import (
    calculate_composite_index_task,
    calculate_district_leaderboard_task,
    calculate_single_district_task,
)

__all__ = [
    "ingest_source_task",
    "ingest_csv_task",
    "scrape_url_task",
    "normalize_and_bind_task",
    "calculate_composite_index_task",
    "calculate_district_leaderboard_task",
    "calculate_single_district_task",
    "poll_outbox_events_task",
    "process_pending_outbox_unwind_batch",
    "BatchNeo4jOutboxProjector",
]
