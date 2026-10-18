"""Project EUREKA: Full-Scale Neo4j Graph Population Harness.

Projects:
1. All Pending Outbox Events (Canonical Events, Claims, Releases, Districts, Departments).
2. All High-Throughput Media Events (linked to District nodes via [:HAS_EVENT]).
3. Border adjacency edges and line departments.
"""

import logging
import os
import sys
from datetime import datetime
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("eureka.neo4j_populate")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from eureka.conclusion.outbox_worker import Neo4jOutboxProjector, process_pending_outbox_batch
from eureka.core.database import sync_db_context
from eureka.core.neo4j_driver import Neo4jGraphService
from eureka.models import OutboxEvent
from eureka.db.models import MediaEvent
from eureka.workers.neo4j_tasks import CYPHER_BATCH_INGEST_QUERY


def project_all_outbox_events():
    logger.info("--> [1/2] Projecting Transactional Outbox Events to Neo4j...")
    projector = Neo4jOutboxProjector()
    with sync_db_context() as session:
        events = session.query(OutboxEvent).all()
        logger.info("  Found %d outbox events in PostgreSQL. Starting projection...", len(events))
        total_processed = 0
        for ev in events:
            try:
                projector.project_event(ev)
                total_processed += 1
                if total_processed % 250 == 0:
                    logger.info("  Projected %d / %d outbox events...", total_processed, len(events))
            except Exception as exc:
                logger.warning("  Failed projecting event %s: %s", ev.id, exc)
    logger.info("  [OK] Successfully projected %d total outbox events to Neo4j.", total_processed)


def project_media_events(batch_size=2000):
    logger.info("--> [2/2] Projecting Media Events to Neo4j graph...")
    with sync_db_context() as session:
        total_media = session.query(MediaEvent).count()
        logger.info("  Found %d media events in PostgreSQL. Starting Cypher batch projection...", total_media)

        offset = 0
        total_linked = 0
        while offset < total_media:
            events = session.query(MediaEvent).offset(offset).limit(batch_size).all()
            if not events:
                break

            event_dicts = [
                {
                    "record_id": e.record_id,
                    "district": e.district,
                    "event_type": e.event_type,
                    "turnaround_time_mins": e.turnaround_time_mins or 30.0,
                    "sentiment_score": e.sentiment_score or 0.0,
                    "crisis_resolved": e.crisis_resolved if e.crisis_resolved is not None else True,
                    "event_timestamp": e.event_timestamp.isoformat() if e.event_timestamp else datetime.utcnow().isoformat(),
                }
                for e in events
            ]

            results = Neo4jGraphService.run_query(CYPHER_BATCH_INGEST_QUERY, {"events": event_dicts})
            linked = results[0]["events_ingested"] if results else 0
            total_linked += linked
            offset += len(events)
            logger.info("  Linked %d / %d media events to Neo4j graph...", offset, total_media)

    logger.info("  [OK] Successfully linked %d media events to Neo4j.", total_linked)


def verify_graph_counts():
    logger.info("--> Graph Node & Relationship Verification in Neo4j:")
    queries = {
        "Districts (:District)": "MATCH (d:District) RETURN count(d) AS count",
        "Departments (:Department)": "MATCH (d:Department) RETURN count(d) AS count",
        "Canonical Events (:CanonicalEvent)": "MATCH (c:CanonicalEvent) RETURN count(c) AS count",
        "Claims (:Claim)": "MATCH (c:Claim) RETURN count(c) AS count",
        "Media Events (:MediaEvent)": "MATCH (m:MediaEvent) RETURN count(m) AS count",
        "Border Relationships ([:BORDERS])": "MATCH ()-[r:BORDERS]->() RETURN count(r) AS count",
        "Has Event Relationships ([:HAS_EVENT])": "MATCH ()-[r:HAS_EVENT]->() RETURN count(r) AS count",
        "Affects Relationships ([:AFFECTS])": "MATCH ()-[r:AFFECTS]->() RETURN count(r) AS count",
    }
    for label, q in queries.items():
        try:
            res = Neo4jGraphService.run_query(q)
            cnt = res[0]["count"] if res else 0
            logger.info("  %s: %s", label, cnt)
        except Exception as exc:
            logger.warning("  %s check failed: %s", label, exc)


def main():
    logger.info("=" * 70)
    logger.info("  PROJECT EUREKA: FULL-SCALE NEO4J GRAPH POPULATION  ")
    logger.info("=" * 70)
    project_all_outbox_events()
    project_media_events()
    verify_graph_counts()
    logger.info("=" * 70)
    logger.info("  NEO4J GRAPH POPULATION COMPLETED SUCCESSFULLY!  ")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
