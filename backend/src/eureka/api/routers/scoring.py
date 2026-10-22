"""100-Point Composite Index API router."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eureka.api.auth import TokenData, require_roles
from eureka.core.database import get_async_db
from eureka.models.entities import PillarScoreSnapshot
from eureka.models.enums import UserRole
from eureka.scoring.scoring_engine import CompositeScoringEngine
from eureka.tasks.scoring_tasks import calculate_composite_index_task

router = APIRouter(prefix="/api/v1/scoring", tags=["100-Point Composite Index"])


@router.get("/leaderboard")
async def get_district_leaderboard(
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK])),
):
    """Fetch ranked performance leaderboard across all 36 Maharashtra districts."""
    leaderboard = CompositeScoringEngine.compute_district_scores_from_csv()
    return {
        "status": "success",
        "total_districts": len(leaderboard),
        "leaderboard": leaderboard,
    }


@router.get("/district/{district_id}")
async def get_district_score_breakdown(
    district_id: int,
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK])),
):
    """Fetch full 4-pillar score breakdown for a specific district."""
    district_score = CompositeScoringEngine.get_district_score(district_id)
    if not district_score:
        raise HTTPException(status_code=404, detail=f"District {district_id} not found")
    return district_score


@router.get("/latest")
async def get_latest_scores(
    db: AsyncSession = Depends(get_async_db),
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK])),
):
    """Fetch the most recent 100-Point Composite Index snapshot across all 4 pillars."""
    stmt = select(PillarScoreSnapshot).order_by(PillarScoreSnapshot.created_at.desc()).limit(1)
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if not snapshot:
        raise HTTPException(status_code=404, detail="No scoring snapshots found yet")

    return {
        "id": str(snapshot.id),
        "total_composite_score": snapshot.total_composite_score,
        "pillars": {
            "volume_score": snapshot.volume_score,
            "sentiment_score": snapshot.sentiment_score,
            "crisis_sla_score": snapshot.crisis_sla_score,
        },
        "window_start": snapshot.window_start.isoformat(),
        "window_end": snapshot.window_end.isoformat(),
        "metadata": snapshot.calculation_metadata,
        "created_at": snapshot.created_at.isoformat(),
    }


@router.post("/calculate")
async def trigger_score_calculation(
    window_hours: int = 24,
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN])),
):
    """Trigger an immediate Celery task to recalculate 100-point composite index."""
    task = calculate_composite_index_task.delay(window_hours=window_hours)
    return {
        "status": "dispatched",
        "task_id": task.id,
        "window_hours": window_hours,
    }
