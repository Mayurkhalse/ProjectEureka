"""Celery tasks for QUAD Ingestion Subsystem (Lanes 1 to 4 + CSV Adapter)."""

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from sqlalchemy import select

from eureka.core.celery_app import celery_app
from eureka.core.database import sync_db_context
from eureka.models.orm import IngestionRun, RawEvent, SourceRegistry
from eureka.models.enums import IngestionRunStatus, SourceLane
from eureka.quad_ingestion.api_connectors import GovApiConnector, PortalApiConnector
from eureka.quad_ingestion.crawl4ai_scraper import Crawl4AIScraperService
from eureka.quad_ingestion.csv_adapter import CSVAdapter

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="eureka.quad_ingestion.tasks.ingest_source_task",
    max_retries=3,
    default_retry_delay=10,
)
def ingest_source_task(self, source_id: str) -> Dict[str, Any]:
    """Execute batch ingestion for a registered source across its designated QUAD lane or CSV adapter."""
    source_uuid = uuid.UUID(source_id)

    with sync_db_context() as session:
        source = session.get(SourceRegistry, source_uuid)
        if not source:
            logger.error("SourceRegistry %s not found", source_id)
            return {"status": "error", "message": f"Source {source_id} not found"}

        if not source.is_active:
            logger.info("SourceRegistry %s is disabled; skipping", source.name)
            return {"status": "skipped", "message": "Source inactive"}

        run = IngestionRun(
            id=uuid.uuid4(),
            source_id=source.id,
            status=IngestionRunStatus.STARTED,
            items_ingested=0,
            errors_count=0,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.commit()
        run_id = run.id

    try:
        with sync_db_context() as session:
            source = session.get(SourceRegistry, source_uuid)
            raw_events: List[RawEvent] = []

            # Check if source is configured for CSV adapter bridge
            if source.config_json and ("csv_file" in source.config_json or source.base_url.endswith(".csv")):
                adapter = CSVAdapter()
                raw_events = adapter.ingest_source(session, source, run_id)
            elif source.lane == SourceLane.LANE_1_API_GOV:
                connector = GovApiConnector()
                raw_events = connector.ingest_source(session, source, run_id)
            elif source.lane == SourceLane.LANE_2_API_PORTAL:
                connector = PortalApiConnector()
                raw_events = connector.ingest_source(session, source, run_id)
            elif source.lane in (SourceLane.LANE_3_SCRAPE_WEB, SourceLane.LANE_4_SCRAPE_DOM):
                scraper = Crawl4AIScraperService()
                raw_events = scraper.ingest_source(session, source, run_id)
            else:
                raise ValueError(f"Unsupported source lane: {source.lane}")

            # Update IngestionRun to COMPLETED
            run = session.get(IngestionRun, run_id)
            run.status = IngestionRunStatus.COMPLETED
            run.items_ingested = len(raw_events)
            run.completed_at = datetime.now(timezone.utc)

            source.last_polled_at = datetime.now(timezone.utc)
            session.commit()

            raw_ids = [str(r.id) for r in raw_events]

        logger.info(
            "Ingestion run %s completed: %d raw events persisted for source '%s'",
            run_id,
            len(raw_ids),
            source.name,
        )

        # Trigger downstream IRF binding for each raw event
        try:
            from eureka.tasks.irf_tasks import normalize_and_bind_task
            for raw_id in raw_ids:
                normalize_and_bind_task.delay(raw_id)
        except Exception as exc:
            logger.warning("Downstream dispatch warning (IRF binding): %s", exc)

        return {
            "status": "success",
            "run_id": str(run_id),
            "source_id": str(source_id),
            "items_ingested": len(raw_ids),
            "raw_event_ids": raw_ids,
        }

    except Exception as exc:
        logger.error("Ingestion run %s failed: %s", run_id, exc, exc_info=True)
        with sync_db_context() as session:
            run = session.get(IngestionRun, run_id)
            if run:
                run.status = IngestionRunStatus.FAILED
                run.errors_count = 1
                run.error_log = {"error": str(exc)}
                run.completed_at = datetime.now(timezone.utc)
                session.commit()
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="eureka.quad_ingestion.tasks.ingest_csv_task",
    max_retries=2,
    default_retry_delay=5,
)
def ingest_csv_task(
    self,
    csv_filename: str,
    lane: str = "LANE_1_API_GOV",
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Ingest records from a benchmark CSV file directly into raw_events using CSVAdapter."""
    adapter = CSVAdapter()
    file_path = adapter.resolve_file_path(csv_filename)

    lane_enum = SourceLane[lane] if lane in SourceLane.__members__ else SourceLane.LANE_1_API_GOV

    with sync_db_context() as session:
        # Find or create a registered source for this CSV
        source_name = f"CSV Import: {Path(csv_filename).name}"
        stmt = select(SourceRegistry).where(SourceRegistry.name == source_name)
        source = session.execute(stmt).scalar_one_or_none()
        if not source:
            source = SourceRegistry(
                id=uuid.uuid4(),
                name=source_name,
                lane=lane_enum,
                base_url=str(file_path),
                config_json={"csv_file": csv_filename, "limit": limit},
                is_active=True,
            )
            session.add(source)
            session.flush()

        run = IngestionRun(
            id=uuid.uuid4(),
            source_id=source.id,
            status=IngestionRunStatus.STARTED,
            items_ingested=0,
            errors_count=0,
            started_at=datetime.now(timezone.utc),
        )
        session.add(run)
        session.commit()
        run_id = run.id
        source_id = source.id

    try:
        with sync_db_context() as session:
            raw_events = adapter.ingest_file(
                session=session,
                file_path=file_path,
                lane=lane_enum,
                source_id=source_id,
                ingestion_run_id=run_id,
                limit=limit,
            )

            run = session.get(IngestionRun, run_id)
            run.status = IngestionRunStatus.COMPLETED
            run.items_ingested = len(raw_events)
            run.completed_at = datetime.now(timezone.utc)
            session.commit()

            raw_ids = [str(r.id) for r in raw_events]

        logger.info(
            "CSV import task %s completed: %d raw events ingested from %s",
            run_id,
            len(raw_ids),
            csv_filename,
        )

        # Trigger downstream IRF binding
        try:
            from eureka.tasks.irf_tasks import normalize_and_bind_task
            for raw_id in raw_ids:
                normalize_and_bind_task.delay(raw_id)
        except Exception as exc:
            logger.warning("Downstream IRF binding dispatch warning: %s", exc)

        return {
            "status": "success",
            "run_id": str(run_id),
            "source_id": str(source_id),
            "csv_filename": csv_filename,
            "items_ingested": len(raw_ids),
            "raw_event_ids": raw_ids,
        }

    except Exception as exc:
        logger.error("CSV import task failed for %s: %s", csv_filename, exc, exc_info=True)
        with sync_db_context() as session:
            run = session.get(IngestionRun, run_id)
            if run:
                run.status = IngestionRunStatus.FAILED
                run.errors_count = 1
                run.error_log = {"error": str(exc)}
                run.completed_at = datetime.now(timezone.utc)
                session.commit()
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="eureka.quad_ingestion.tasks.scrape_url_task",
    max_retries=2,
    default_retry_delay=5,
)
def scrape_url_task(
    self,
    url: str,
    lane: str = "LANE_3_SCRAPE_WEB",
    source_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Ad-hoc single URL scraping task using Crawl4AI."""
    try:
        scraper = Crawl4AIScraperService()
        result = scraper.scrape_url_sync(url)
        return {
            "status": "success",
            "url": url,
            "lane": lane,
            "title": result.get("title", ""),
            "content_length": len(result.get("markdown", "")),
            "engine": result.get("engine", "crawl4ai"),
        }
    except Exception as exc:
        logger.error("scrape_url_task error for %s: %s", url, exc)
        raise self.retry(exc=exc)
