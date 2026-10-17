"""Unit tests for Neo4j Cypher batch ingestion worker in Project EUREKA."""

from unittest.mock import MagicMock, patch
import pytest

from eureka.workers.neo4j_tasks import ingest_neo4j_batch_task, CYPHER_BATCH_INGEST_QUERY


def test_cypher_batch_ingest_query_structure():
    assert "UNWIND $events AS event" in CYPHER_BATCH_INGEST_QUERY
    assert "MERGE (d:District {name: event.district})" in CYPHER_BATCH_INGEST_QUERY
    assert "MERGE (e:MediaEvent {id: event.record_id})" in CYPHER_BATCH_INGEST_QUERY
    assert "MERGE (d)-[:HAS_EVENT]->(e)" in CYPHER_BATCH_INGEST_QUERY
    assert "RETURN count(e) AS events_ingested" in CYPHER_BATCH_INGEST_QUERY


def test_ingest_neo4j_batch_task_success():
    events = [
        {
            "record_id": "rec-001",
            "district": "Thane",
            "event_type": "News Article",
            "turnaround_time_mins": 30.0,
            "sentiment_score": 0.85,
            "crisis_resolved": True,
            "event_timestamp": "2026-10-17T08:00:00Z",
        },
        {
            "record_id": "rec-002",
            "district": "Palghar",
            "event_type": "Tweet",
            "turnaround_time_mins": 15.0,
            "sentiment_score": -0.2,
            "crisis_resolved": False,
            "event_timestamp": "2026-10-17T08:15:00Z",
        },
    ]

    with patch("eureka.workers.neo4j_tasks.Neo4jGraphService.run_query") as mock_run_query:
        mock_run_query.return_value = [{"events_ingested": 2}]

        # Call underlying task using celery's apply for synchronous execution
        res = ingest_neo4j_batch_task.apply(args=[events])
        result = res.result

        assert result["status"] == "success"
        assert result["nodes_linked"] == 2
        mock_run_query.assert_called_once_with(CYPHER_BATCH_INGEST_QUERY, {"events": events})


def test_ingest_neo4j_batch_task_empty():
    with patch("eureka.workers.neo4j_tasks.Neo4jGraphService.run_query") as mock_run_query:
        mock_run_query.return_value = []

        res = ingest_neo4j_batch_task.apply(args=[[]])
        result = res.result

        assert result["status"] == "success"
        assert result["nodes_linked"] == 0
