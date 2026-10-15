"""Celery application instance configuration for Project EUREKA."""

from celery import Celery
from kombu import Exchange, Queue

from eureka.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "eureka",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=[
        "eureka.quad_ingestion.tasks",
        "eureka.irf_binding.binding_tasks",
        "eureka.processor.muril_tasks",
        "eureka.scoring.scoring_tasks",
        "eureka.conclusion.outbox_worker",
        "eureka.tasks.quad_tasks",
        "eureka.tasks.irf_tasks",
        "eureka.tasks.scoring_tasks",
        "eureka.tasks.outbox_tasks",
    ],
)

# Queues and exchanges configuration
default_exchange = Exchange("default", type="direct")
quad_exchange = Exchange("quad_ingestion", type="direct")
irf_exchange = Exchange("irf_binding", type="direct")
processor_exchange = Exchange("processor", type="direct")
outbox_exchange = Exchange("outbox", type="direct")

celery_app.conf.task_queues = (
    Queue("default", default_exchange, routing_key="default"),
    Queue("quad_ingestion", quad_exchange, routing_key="quad_ingestion"),
    Queue("irf_binding", irf_exchange, routing_key="irf_binding"),
    Queue("processor", processor_exchange, routing_key="processor"),
    Queue("outbox", outbox_exchange, routing_key="outbox"),
)

celery_app.conf.task_default_queue = "default"
celery_app.conf.task_default_exchange = "default"
celery_app.conf.task_default_routing_key = "default"

# Task routing
celery_app.conf.task_routes = {
    "eureka.quad_ingestion.tasks.*": {"queue": "quad_ingestion", "routing_key": "quad_ingestion"},
    "eureka.tasks.quad_tasks.*": {"queue": "quad_ingestion", "routing_key": "quad_ingestion"},
    "eureka.irf_binding.binding_tasks.*": {"queue": "irf_binding", "routing_key": "irf_binding"},
    "eureka.tasks.irf_tasks.*": {"queue": "irf_binding", "routing_key": "irf_binding"},
    "eureka.processor.muril_tasks.*": {"queue": "processor", "routing_key": "processor"},
    "eureka.scoring.scoring_tasks.*": {"queue": "processor", "routing_key": "processor"},
    "eureka.tasks.scoring_tasks.*": {"queue": "processor", "routing_key": "processor"},
    "eureka.conclusion.outbox_worker.*": {"queue": "outbox", "routing_key": "outbox"},
    "eureka.tasks.outbox_tasks.*": {"queue": "outbox", "routing_key": "outbox"},
}

# General worker settings
celery_app.conf.update(
    task_always_eager=settings.CELERY_TASK_ALWAYS_EAGER,
    task_eager_propagates=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,               # Idempotent task design - ack after processing
    task_reject_on_worker_lost=True,   # Re-queue on worker crash
    worker_prefetch_multiplier=1,      # Fair distribution across workers
    broker_connection_retry_on_startup=True,
)

# Periodic schedule (Celery Beat)
celery_app.conf.beat_schedule = {
    "poll-outbox-events-every-5s": {
        "task": "eureka.conclusion.outbox_worker.process_outbox_events_task",
        "schedule": float(settings.OUTBOX_POLL_INTERVAL_SECONDS),
        "options": {"queue": "outbox"},
    },
    "calculate-100-point-index-every-15m": {
        "task": "eureka.scoring.scoring_tasks.calculate_composite_index_task",
        "schedule": 900.0,  # 15 minutes
        "options": {"queue": "processor"},
    },
}
