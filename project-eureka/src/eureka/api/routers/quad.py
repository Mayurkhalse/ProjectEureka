"""QUAD Ingestion API endpoints for triggering Celery ingestion tasks."""

import uuid
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, HttpUrl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eureka.api.auth import TokenData, require_roles
from eureka.core.database import get_async_db
from eureka.models.entities import SourceRegistry
from eureka.models.enums import SourceLane, UserRole
from eureka.models.schemas import CSVImportRequest
from eureka.tasks.quad_tasks import ingest_csv_task, ingest_source_task, scrape_url_task

router = APIRouter(prefix="/api/v1/quad", tags=["QUAD Ingestion"])


class SourceCreateSchema(BaseModel):
    name: str
    lane: SourceLane
    base_url: str
    config_json: Dict[str, Any] = {}
    poll_interval_sec: int = 300


class ScrapeRequestSchema(BaseModel):
    url: str
    lane: SourceLane = SourceLane.LANE_3_SCRAPE_WEB
    css_selector: Optional[str] = None


@router.post("/import/csv")
async def import_csv_dataset(
    payload: CSVImportRequest,
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DIO_DESK])),
):
    """Trigger asynchronous ingestion of a benchmark CSV dataset via CSVAdapter."""
    lane_str = payload.lane.value if hasattr(payload.lane, "value") else str(payload.lane)
    task = ingest_csv_task.delay(
        csv_filename=payload.csv_file,
        lane=lane_str,
    )
    return {
        "status": "dispatched",
        "task_id": task.id,
        "csv_file": payload.csv_file,
        "lane": lane_str,
        "adapter": "CSVAdapter",
    }


@router.post("/ingest/{source_id}")
async def trigger_source_ingestion(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_async_db),
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DIO_DESK])),
):
    """Trigger an asynchronous Celery ingestion task for a specific registered source."""
    source = await db.get(SourceRegistry, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    task = ingest_source_task.delay(str(source.id))
    return {
        "status": "dispatched",
        "task_id": task.id,
        "source_id": str(source.id),
        "source_name": source.name,
        "lane": source.lane,
    }


@router.post("/scrape")
async def trigger_adhoc_scrape(
    payload: ScrapeRequestSchema,
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DIO_DESK])),
):
    """Trigger an ad-hoc single URL crawl using Crawl4AI."""
    task = scrape_url_task.delay(payload.url, lane=payload.lane.value)
    return {
        "status": "dispatched",
        "task_id": task.id,
        "url": payload.url,
        "lane": payload.lane,
    }


@router.get("/sources")
async def list_sources(
    db: AsyncSession = Depends(get_async_db),
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK])),
):
    """List all registered ingestion sources across QUAD lanes."""
    stmt = select(SourceRegistry).order_by(SourceRegistry.name.asc())
    result = await db.execute(stmt)
    sources = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "lane": s.lane,
            "base_url": s.base_url,
            "is_active": s.is_active,
            "poll_interval_sec": s.poll_interval_sec,
            "last_polled_at": s.last_polled_at.isoformat() if s.last_polled_at else None,
        }
        for s in sources
    ]
