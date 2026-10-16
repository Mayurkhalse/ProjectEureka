"""Asynchronous Neo4j graph ingestion worker using Cypher batching."""

from typing import Any, Dict, List
from celery.utils.log import get_task_logger

from eureka.core.celery_app import celery_app
from eureka.core.neo4j_driver import Neo4jGraphService

logger = get_task_logger(__name__)

CYPHER_BATCH_INGEST_QUERY = """
UNWIND $events AS event
MERGE (d:District {name: event.district})
ON CREATE SET d.code = event.district
MERGE (e:MediaEvent {id: event.record_id})
SET e.event_type = event.event_type,
    e.turnaround_time_mins = toFloat(event.turnaround_time_mins),
    e.sentiment_score = toFloat(event.sentiment_score),
    e.crisis_resolved = toBoolean(event.crisis_resolved),
    e.timestamp = toString(event.event_timestamp)
MERGE (d)-[:HAS_EVENT]->(e)
RETURN count(e) AS events_ingested
"""


@celery_app.task(bind=True, name="eureka.workers.ingest_neo4j_batch_task")
def ingest_neo4j_batch_task(self, events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Ingest a batch of media events into the Neo4j graph cluster using Cypher.

    Args:
        events: List of event dictionaries containing district, record_id, and metrics.
    """
    logger.info("Executing Cypher batch graph ingestion for %s events...", len(events))
    try:
        results = Neo4jGraphService.run_query(CYPHER_BATCH_INGEST_QUERY, {"events": events})
        count = results[0]["events_ingested"] if results else 0
        logger.info("Successfully linked %s graph nodes in Neo4j.", count)
        return {
            "status": "success",
            "task_id": self.request.id,
            "nodes_linked": count,
        }
    except Exception as exc:
        logger.error("Neo4j Cypher batch ingestion failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=5, max_retries=3)
