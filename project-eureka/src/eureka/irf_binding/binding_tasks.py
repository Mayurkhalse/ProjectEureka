"""IRF Binding Celery tasks re-export from eureka.tasks.irf_tasks."""

from eureka.tasks.irf_tasks import normalize_and_bind_task

__all__ = [
    "normalize_and_bind_task",
]
