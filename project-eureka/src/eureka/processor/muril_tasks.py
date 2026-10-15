"""Celery tasks for MuRIL sentiment classification."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from eureka.core.celery_app import celery_app
from eureka.core.database import sync_db_context
from eureka.models.entities import CanonicalEvent, OutboxEvent
from eureka.models.enums import AggregateType, OutboxEventStatus
from eureka.processor.muril_head import MuRILSentimentPipeline

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="eureka.processor.muril_tasks.process_muril_sentiment_task",
    max_retries=2,
    default_retry_delay=5,
)
def process_muril_sentiment_task(self, canonical_event_id: str) -> Dict[str, Any]:
    """Execute MuRIL multilingual sentiment inference for a CanonicalEvent."""
    canonical_uuid = uuid.UUID(canonical_event_id)

    with sync_db_context() as session:
        canonical = session.get(CanonicalEvent, canonical_uuid)
        if not canonical:
            logger.error("CanonicalEvent %s not found for sentiment analysis", canonical_event_id)
            return {"status": "error", "message": "CanonicalEvent not found"}

        lang_code = canonical.primary_language.value if hasattr(canonical.primary_language, "value") else str(canonical.primary_language)
        result = MuRILSentimentPipeline.analyze(canonical.summary, lang=lang_code)

        canonical.sentiment_label = result.label
        canonical.sentiment_score = result.polarity_score
        canonical.last_updated_at = datetime.now(timezone.utc)

        # Emit OutboxEvent to update Neo4j node
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type=AggregateType.CANONICAL_EVENT,
            aggregate_id=str(canonical.id),
            event_type="UPDATED",
            payload={
                "title": canonical.title,
                "summary": canonical.summary,
                "sentiment_label": result.label,
                "sentiment_score": result.polarity_score,
                "status": canonical.status.value if hasattr(canonical.status, "value") else str(canonical.status),
                "last_updated_at": canonical.last_updated_at.isoformat(),
            },
            status=OutboxEventStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(outbox)
        session.commit()

        logger.info(
            "CanonicalEvent %s classified: %s (polarity: %.3f, confidence: %.2f)",
            canonical_event_id,
            result.label,
            result.polarity_score,
            result.confidence,
        )

        return {
            "status": "success",
            "canonical_id": canonical_event_id,
            "sentiment_label": result.label,
            "sentiment_score": result.polarity_score,
            "confidence": result.confidence,
        }
