"""Celery tasks for SemIf-OpenJev IRF Binding Subsystem."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from eureka.core.celery_app import celery_app
from eureka.core.database import sync_db_context
from eureka.irf_binding.engine import SemIfOpenJevBindingEngine, TextNormalizer
from eureka.models.orm import NormalizedRecord, OutboxEvent, RawEvent
from eureka.models.enums import AggregateType, OutboxEventStatus

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="eureka.irf_binding.binding_tasks.normalize_and_bind_task",
    max_retries=3,
    default_retry_delay=5,
)
def normalize_and_bind_task(self, raw_event_id: str) -> Dict[str, Any]:
    """Normalize raw event content, identify language, and semantically bind via SemIf-OpenJev."""
    raw_uuid = uuid.UUID(raw_event_id)

    with sync_db_context() as session:
        raw_event = session.get(RawEvent, raw_uuid)
        if not raw_event:
            logger.error("RawEvent %s not found for normalization", raw_event_id)
            return {"status": "error", "message": "RawEvent not found"}

        # 1. Text normalization & entity extraction
        norm_result = TextNormalizer.normalize(raw_event.raw_content, raw_event.raw_metadata)

        normalized_rec = NormalizedRecord(
            id=uuid.uuid4(),
            raw_event_id=raw_event.id,
            title=norm_result.title,
            cleaned_text=norm_result.cleaned_text,
            detected_language=norm_result.language,
            script=norm_result.script,
            normalized_timestamp=norm_result.normalized_timestamp,
            entities=norm_result.entities,
            claims=norm_result.claims,
        )
        session.add(normalized_rec)
        session.flush()

        # 2. Bind with SemIf-OpenJev decision logic
        canonical, decision = SemIfOpenJevBindingEngine.bind_record(session, normalized_rec)

        # 3. Emit Release node outbox event for Neo4j projection
        release_outbox = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type=AggregateType.RELEASE,
            aggregate_id=str(normalized_rec.id),
            event_type="CREATED",
            payload={
                "title": normalized_rec.title,
                "source": raw_event.raw_metadata.get("ingested_via", "QUAD"),
                "url": raw_event.raw_metadata.get("url", ""),
                "timestamp": normalized_rec.normalized_timestamp.isoformat(),
                "canonical_event_id": str(canonical.id),
            },
            status=OutboxEventStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(release_outbox)
        session.commit()

        canonical_id = str(canonical.id)
        decision_type = decision.decision_type.value if hasattr(decision.decision_type, "value") else str(decision.decision_type)
        logic_primitive = decision.logic_primitive

    logger.info(
        "Normalized record %s bound to CanonicalEvent %s via Open-Jev %s (%s)",
        normalized_rec.id,
        canonical_id,
        logic_primitive,
        decision_type,
    )

    # Dispatch to downstream processor for MuRIL sentiment analysis
    try:
        from eureka.processor.muril_tasks import process_muril_sentiment_task
        process_muril_sentiment_task.delay(canonical_id)
    except Exception as exc:
        logger.warning("Downstream MuRIL dispatch warning: %s", exc)

    return {
        "status": "success",
        "normalized_id": str(normalized_rec.id),
        "canonical_id": canonical_id,
        "decision": decision_type,
        "logic_primitive": logic_primitive,
    }
