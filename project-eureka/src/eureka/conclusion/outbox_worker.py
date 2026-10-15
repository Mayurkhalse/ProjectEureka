"""Transactional Outbox Worker for Neo4j Spatio-Temporal Graph Projection.

PostgreSQL and Neo4j do not share ACID transactions.
This worker polls outbox_events in PostgreSQL using `FOR UPDATE SKIP LOCKED`
and executes idempotent parameterized MERGE statements in Neo4j.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from eureka.core.celery_app import celery_app
from eureka.core.config import get_settings
from eureka.core.database import sync_db_context
from eureka.core.neo4j_driver import Neo4jGraphService
from eureka.models.enums import AggregateType, OutboxEventStatus
from eureka.models.entities import OutboxEvent

logger = logging.getLogger(__name__)
settings = get_settings()


class Neo4jOutboxProjector:
    """Processes transactional outbox events by executing idempotent Cypher MERGE queries."""

    def __init__(self, driver_service=Neo4jGraphService):
        self.driver_service = driver_service

    def project_event(self, event: OutboxEvent) -> bool:
        """Projects a single OutboxEvent to Neo4j. Returns True on success, False on failure."""
        payload = event.payload or {}
        aggregate_type = event.aggregate_type
        aggregate_id = event.aggregate_id

        try:
            if aggregate_type == AggregateType.CANONICAL_EVENT or aggregate_type == "CanonicalEvent":
                self._project_canonical_event(aggregate_id, payload)
            elif aggregate_type == AggregateType.RELEASE or aggregate_type == "Release":
                self._project_release(aggregate_id, payload)
            elif aggregate_type == AggregateType.DISTRICT or aggregate_type == "District":
                self._project_district(aggregate_id, payload)
            elif aggregate_type == AggregateType.DEPARTMENT or aggregate_type == "Department":
                self._project_department(aggregate_id, payload)
            elif aggregate_type == AggregateType.CLAIM or aggregate_type == "Claim":
                self._project_claim(aggregate_id, payload)
            elif aggregate_type == AggregateType.EVENT_SOURCE_LINK or aggregate_type == "EventSourceLink":
                self._project_event_source_link(aggregate_id, payload)
            else:
                logger.warning("Unrecognized aggregate type in outbox: %s", aggregate_type)
            return True
        except Exception as exc:
            logger.error(
                "Failed to project outbox event %s (aggregate: %s, id: %s) to Neo4j: %s",
                event.id,
                aggregate_type,
                aggregate_id,
                exc,
                exc_info=True,
            )
            raise

    def _project_canonical_event(self, event_id: str, payload: Dict[str, Any]) -> None:
        """Merge CanonicalEvent node and spatio-temporal relationships (AFFECTS, RELATES_TO)."""
        cypher = """
        MERGE (e:CanonicalEvent {id: $id})
        SET e.title = $title,
            e.summary = $summary,
            e.status = $status,
            e.verification_status = $verification_status,
            e.primary_language = $primary_language,
            e.first_detected_at = $first_detected_at,
            e.last_updated_at = $last_updated_at
        """
        params = {
            "id": event_id,
            "title": payload.get("title", ""),
            "summary": payload.get("summary", ""),
            "status": payload.get("status", "pending_review"),
            "verification_status": payload.get("verification_status", "UNVERIFIED"),
            "primary_language": payload.get("primary_language", "mr"),
            "first_detected_at": payload.get("first_detected_at", datetime.now(timezone.utc).isoformat()),
            "last_updated_at": payload.get("last_updated_at", datetime.now(timezone.utc).isoformat()),
        }
        self.driver_service.run_query(cypher, params)

        # District edge: (:CanonicalEvent)-[:AFFECTS]->(:District)
        district_code = payload.get("district_code")
        if district_code:
            district_cypher = """
            MERGE (e:CanonicalEvent {id: $event_id})
            MERGE (d:District {code: $district_code})
            ON CREATE SET d.name = $district_name, d.state = 'Maharashtra'
            MERGE (e)-[:AFFECTS]->(d)
            """
            self.driver_service.run_query(
                district_cypher,
                {
                    "event_id": event_id,
                    "district_code": district_code,
                    "district_name": payload.get("district_name", district_code),
                },
            )

        # Department edge: (:CanonicalEvent)-[:RELATES_TO]->(:Department)
        dept_code = payload.get("department_code")
        if dept_code:
            dept_cypher = """
            MERGE (e:CanonicalEvent {id: $event_id})
            MERGE (dep:Department {code: $dept_code})
            ON CREATE SET dep.name = $dept_name
            MERGE (e)-[:RELATES_TO]->(dep)
            """
            self.driver_service.run_query(
                dept_cypher,
                {
                    "event_id": event_id,
                    "dept_code": dept_code,
                    "dept_name": payload.get("department_name", dept_code),
                },
            )

    def _project_release(self, release_id: str, payload: Dict[str, Any]) -> None:
        """Merge Release node and (:Release)-[:REPORTS_ON]->(:CanonicalEvent) edge."""
        cypher = """
        MERGE (r:Release {id: $id})
        SET r.title = $title,
            r.source = $source,
            r.url = $url,
            r.timestamp = $timestamp
        """
        params = {
            "id": release_id,
            "title": payload.get("title", ""),
            "source": payload.get("source", ""),
            "url": payload.get("url", ""),
            "timestamp": payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
        }
        self.driver_service.run_query(cypher, params)

        canonical_event_id = payload.get("canonical_event_id")
        if canonical_event_id:
            link_cypher = """
            MERGE (r:Release {id: $release_id})
            MERGE (e:CanonicalEvent {id: $canonical_event_id})
            MERGE (r)-[:REPORTS_ON]->(e)
            """
            self.driver_service.run_query(
                link_cypher,
                {"release_id": release_id, "canonical_event_id": canonical_event_id},
            )

    def _project_district(self, code: str, payload: Dict[str, Any]) -> None:
        """Merge District node."""
        cypher = """
        MERGE (d:District {code: $code})
        SET d.name = $name,
            d.state = coalesce($state, 'Maharashtra')
        """
        params = {
            "code": code,
            "name": payload.get("name", code),
            "state": payload.get("state", "Maharashtra"),
        }
        self.driver_service.run_query(cypher, params)

    def _project_department(self, code: str, payload: Dict[str, Any]) -> None:
        """Merge Department node."""
        cypher = """
        MERGE (dep:Department {code: $code})
        SET dep.name = $name
        """
        params = {
            "code": code,
            "name": payload.get("name", code),
        }
        self.driver_service.run_query(cypher, params)

    def _project_claim(self, claim_id: str, payload: Dict[str, Any]) -> None:
        """Merge Claim node and incident edges (:CanonicalEvent)-[:CONTAINS_CLAIM]->(:Claim)."""
        cypher = """
        MERGE (c:Claim {id: $id})
        SET c.text = $text,
            c.is_rumor = $is_rumor,
            c.refuted = $refuted
        """
        params = {
            "id": claim_id,
            "text": payload.get("text", ""),
            "is_rumor": payload.get("is_rumor", True),
            "refuted": payload.get("refuted", False),
        }
        self.driver_service.run_query(cypher, params)

        canonical_event_id = payload.get("canonical_event_id")
        if canonical_event_id:
            edge_cypher = """
            MERGE (e:CanonicalEvent {id: $canonical_event_id})
            MERGE (c:Claim {id: $claim_id})
            MERGE (e)-[:CONTAINS_CLAIM]->(c)
            """
            self.driver_service.run_query(
                edge_cypher,
                {"canonical_event_id": canonical_event_id, "claim_id": claim_id},
            )

        district_code = payload.get("district_code")
        if district_code:
            claim_dist_cypher = """
            MERGE (c:Claim {id: $claim_id})
            MERGE (d:District {code: $district_code})
            MERGE (c)-[:AFFECTS]->(d)
            """
            self.driver_service.run_query(
                claim_dist_cypher,
                {"claim_id": claim_id, "district_code": district_code},
            )

    def _project_event_source_link(self, link_id: str, payload: Dict[str, Any]) -> None:
        """Merge Release and CanonicalEvent link with similarity metrics."""
        cypher = """
        MERGE (r:Release {id: $release_id})
        MERGE (e:CanonicalEvent {id: $canonical_event_id})
        MERGE (r)-[rel:REPORTS_ON]->(e)
        SET rel.similarity_score = $similarity_score,
            rel.bound_by = $bound_by,
            rel.link_id = $link_id
        """
        params = {
            "link_id": link_id,
            "release_id": payload.get("release_id", payload.get("normalized_record_id")),
            "canonical_event_id": payload.get("canonical_event_id"),
            "similarity_score": payload.get("similarity_score", 1.0),
            "bound_by": payload.get("bound_by", "SemIf-OpenJev"),
        }
        self.driver_service.run_query(cypher, params)


def process_pending_outbox_batch(batch_size: Optional[int] = None) -> int:
    """Fetch pending outbox events using FOR UPDATE SKIP LOCKED and project them to Neo4j."""
    limit = batch_size or settings.OUTBOX_BATCH_SIZE
    projector = Neo4jOutboxProjector()
    processed_count = 0

    with sync_db_context() as session:
        # Select rows with row-level locks so concurrent workers don't collide
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == OutboxEventStatus.PENDING)
            .order_by(OutboxEvent.created_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        events = session.execute(stmt).scalars().all()

        if not events:
            return 0

        for event in events:
            try:
                projector.project_event(event)
                event.status = OutboxEventStatus.PROCESSED
                event.processed_at = datetime.now(timezone.utc)
                event.last_error = None
                processed_count += 1
            except Exception as exc:
                event.retry_count += 1
                event.last_error = str(exc)
                if event.retry_count >= settings.OUTBOX_MAX_RETRIES:
                    event.status = OutboxEventStatus.FAILED
                    logger.error(
                        "OutboxEvent %s reached max retries (%d). Marked FAILED.",
                        event.id,
                        settings.OUTBOX_MAX_RETRIES,
                    )
                else:
                    logger.warning(
                        "OutboxEvent %s failed (attempt %d): %s",
                        event.id,
                        event.retry_count,
                        exc,
                    )
        session.commit()

    logger.info("Outbox worker processed %d/%d pending events", processed_count, len(events))
    return processed_count


@celery_app.task(
    bind=True,
    name="eureka.conclusion.outbox_worker.process_outbox_events_task",
    max_retries=3,
    default_retry_delay=5,
)
def process_outbox_events_task(self):
    """Celery periodic task executing transactional outbox projection."""
    try:
        return process_pending_outbox_batch()
    except Exception as exc:
        logger.error("Error in process_outbox_events_task: %s", exc)
        raise self.retry(exc=exc)
