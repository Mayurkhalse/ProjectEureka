"""Celery tasks for 100-Point Composite Index periodic calculation and district leaderboard."""

import logging
from typing import Any, Dict, List, Optional

from eureka.core.celery_app import celery_app
from eureka.core.database import sync_db_context
from eureka.scoring.scoring_engine import CompositeScoringEngine

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="eureka.scoring.scoring_tasks.calculate_composite_index_task",
    max_retries=2,
    default_retry_delay=10,
)
def calculate_composite_index_task(self, window_hours: int = 24) -> Dict[str, Any]:
    """Periodic Celery task computing the four 25-point pillars and saving snapshot in PostgreSQL."""
    try:
        with sync_db_context() as session:
            snapshot = CompositeScoringEngine.compute_window_scores(session, window_hours=window_hours)
            return {
                "status": "success",
                "snapshot_id": str(snapshot.id),
                "total_composite_score": snapshot.total_composite_score,
                "volume_score": snapshot.volume_score,
                "tat_score": snapshot.tat_score,
                "sentiment_score": snapshot.sentiment_score,
                "crisis_sla_score": snapshot.crisis_sla_score,
            }
    except Exception as exc:
        logger.error("Error calculating composite index snapshot: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="eureka.scoring.scoring_tasks.calculate_district_leaderboard_task",
    max_retries=2,
    default_retry_delay=5,
)
def calculate_district_leaderboard_task(self, seed_dir: Optional[str] = None) -> List[Dict[str, Any]]:
    """Compute ranked leaderboard across all 36 Maharashtra districts."""
    try:
        scores = CompositeScoringEngine.compute_district_scores_from_csv(seed_dir=seed_dir)
        logger.info("Computed leaderboard for %d districts. Top 1: %s (%.2f)", len(scores), scores[0]["district"], scores[0]["total_score"])
        return scores
    except Exception as exc:
        logger.error("Error computing district leaderboard: %s", exc)
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="eureka.scoring.scoring_tasks.calculate_single_district_task",
    max_retries=2,
    default_retry_delay=5,
)
def calculate_single_district_task(self, district_id: int, seed_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Compute score breakdown for a specific district."""
    try:
        return CompositeScoringEngine.get_district_score(district_id, seed_dir=seed_dir)
    except Exception as exc:
        logger.error("Error computing score for district %d: %s", district_id, exc)
        raise self.retry(exc=exc)
