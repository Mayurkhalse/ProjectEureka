"""Unit tests for Neo4jOutboxProjector in Project EUREKA."""

import uuid
from datetime import datetime, timezone
import pytest
from unittest.mock import MagicMock

from eureka.conclusion.outbox_worker import Neo4jOutboxProjector
from eureka.models.entities import OutboxEvent
from eureka.models.enums import AggregateType, OutboxEventStatus


class MockNeo4jDriverService:
    """Mock service capturing queries and parameters executed by Neo4jOutboxProjector."""

    def __init__(self):
        self.queries = []

    def run_query(self, query: str, parameters=None):
        self.queries.append((query.strip(), parameters or {}))
        return []


def test_project_canonical_event():
    mock_service = MockNeo4jDriverService()
    projector = Neo4jOutboxProjector(driver_service=mock_service)

    event_id = str(uuid.uuid4())
    event = OutboxEvent(
        id=uuid.uuid4(),
        aggregate_type=AggregateType.CANONICAL_EVENT,
        aggregate_id=event_id,
        event_type="CREATED",
        payload={
            "title": "CM Announces Drought Relief in Marathwada",
            "summary": "Special package sanctioned for farmers in Chhatrapati Sambhaji Nagar.",
            "status": "pending_review",
            "verification_status": "VERIFIED",
            "primary_language": "mr",
            "district_code": "MH-20",
            "district_name": "Chhatrapati Sambhaji Nagar",
            "department_code": "RELIEF_REHAB",
            "department_name": "Relief and Rehabilitation",
        },
        status=OutboxEventStatus.PENDING,
    )

    success = projector.project_event(event)
    assert success is True
    assert len(mock_service.queries) == 3

    # Check 1: CanonicalEvent node MERGE
    assert "MERGE (e:CanonicalEvent {id: $id})" in mock_service.queries[0][0]
    assert mock_service.queries[0][1]["id"] == event_id

    # Check 2: District MERGE and AFFECTS relationship
    assert "MERGE (d:District {code: $district_code})" in mock_service.queries[1][0]
    assert "MERGE (e)-[:AFFECTS]->(d)" in mock_service.queries[1][0]
    assert mock_service.queries[1][1]["district_code"] == "MH-20"

    # Check 3: Department MERGE and RELATES_TO relationship
    assert "MERGE (dep:Department {code: $dept_code})" in mock_service.queries[2][0]
    assert "MERGE (e)-[:RELATES_TO]->(dep)" in mock_service.queries[2][0]
    assert mock_service.queries[2][1]["dept_code"] == "RELIEF_REHAB"


def test_project_release():
    mock_service = MockNeo4jDriverService()
    projector = Neo4jOutboxProjector(driver_service=mock_service)

    release_id = str(uuid.uuid4())
    canonical_id = str(uuid.uuid4())
    event = OutboxEvent(
        id=uuid.uuid4(),
        aggregate_type=AggregateType.RELEASE,
        aggregate_id=release_id,
        event_type="CREATED",
        payload={
            "title": "Government Resolution Issued on Farm Aid",
            "source": "DGIPR Portal",
            "url": "https://dgipr.maharashtra.gov.in/gr-farm-aid",
            "canonical_event_id": canonical_id,
        },
        status=OutboxEventStatus.PENDING,
    )

    success = projector.project_event(event)
    assert success is True
    assert len(mock_service.queries) == 2

    # Check 1: Release node MERGE
    assert "MERGE (r:Release {id: $id})" in mock_service.queries[0][0]
    # Check 2: REPORTS_ON edge
    assert "MERGE (r)-[:REPORTS_ON]->(e)" in mock_service.queries[1][0]
    assert mock_service.queries[1][1]["canonical_event_id"] == canonical_id


def test_project_claim_and_district():
    mock_service = MockNeo4jDriverService()
    projector = Neo4jOutboxProjector(driver_service=mock_service)

    claim_id = str(uuid.uuid4())
    canonical_id = str(uuid.uuid4())
    event = OutboxEvent(
        id=uuid.uuid4(),
        aggregate_type=AggregateType.CLAIM,
        aggregate_id=claim_id,
        event_type="CREATED",
        payload={
            "text": "Viral message claims aid is cancelled for Beed district",
            "is_rumor": True,
            "refuted": False,
            "canonical_event_id": canonical_id,
            "district_code": "MH-23",
        },
        status=OutboxEventStatus.PENDING,
    )

    success = projector.project_event(event)
    assert success is True
    assert len(mock_service.queries) == 3

    # Check 1: Claim node MERGE
    assert "MERGE (c:Claim {id: $id})" in mock_service.queries[0][0]
    # Check 2: CONTAINS_CLAIM edge
    assert "MERGE (e)-[:CONTAINS_CLAIM]->(c)" in mock_service.queries[1][0]
    # Check 3: AFFECTS District edge
    assert "MERGE (c)-[:AFFECTS]->(d)" in mock_service.queries[2][0]
    assert mock_service.queries[2][1]["district_code"] == "MH-23"
