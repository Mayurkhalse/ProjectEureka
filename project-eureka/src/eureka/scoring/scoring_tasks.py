"""Scoring Celery tasks re-export from eureka.tasks.scoring_tasks."""

from eureka.tasks.scoring_tasks import (
    calculate_composite_index_task,
    calculate_district_leaderboard_task,
    calculate_single_district_task,
)

__all__ = [
    "calculate_composite_index_task",
    "calculate_district_leaderboard_task",
    "calculate_single_district_task",
]
