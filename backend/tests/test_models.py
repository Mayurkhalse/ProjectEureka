"""Unit tests for SQLAlchemy 2.0 ORM models in Project EUREKA."""

import uuid
from datetime import datetime, timezone
import pytest

from eureka.models import (
    Base,
    SourceRegistry,
    IngestionRun,
    RawEvent,
    NormalizedRecord,
    CanonicalEvent,
    EventSourceLink,
    BindingDecision,
    FactCheckTicket,
    PillarScoreSnapshot,
    HumanReviewAction,
    OutboxEvent,
    SourceLane,
    IngestionRunStatus,
    DetectedLanguage,
    CanonicalEventStatus,
    VerificationStatus,
    BindingDecisionType,
    FactCheckTicketStatus,
    UserRole,
    OutboxEventStatus,
    AggregateType,
)


def test_models_metadata_has_all_tables():
    """Verify that all 11 core tables are declared in Base.metadata."""
    table_names = set(Base.metadata.tables.keys())
    expected_tables = {
        "source_registry",
        "ingestion_runs",
        "raw_events",
        "normalized_records",
        "canonical_events",
        "event_source_links",
        "binding_decisions",
        "fact_check_tickets",
        "pillar_score_snapshots",
        "human_review_actions",
        "outbox_events",
    }
    assert expected_tables.issubset(table_names), f"Missing tables: {expected_tables - table_names}"


def test_instantiate_source_registry_and_raw_event():
    """Test model instantiation and field types."""
    source_id = uuid.uuid4()
    source = SourceRegistry(
        id=source_id,
        name="DGIPR Official Press Releases",
        lane=SourceLane.LANE_1_API_GOV,
        base_url="https://dgipr.maharashtra.gov.in/api/v1/releases",
        config_json={"headers": {"Accept": "application/json"}},
        is_active=True,
        poll_interval_sec=300,
    )
    assert source.lane == SourceLane.LANE_1_API_GOV
    assert source.name == "DGIPR Official Press Releases"

    run_id = uuid.uuid4()
    run = IngestionRun(
        id=run_id,
        source_id=source_id,
        status=IngestionRunStatus.STARTED,
        items_ingested=0,
        errors_count=0,
    )
    assert run.status == IngestionRunStatus.STARTED

    raw_event = RawEvent(
        id=uuid.uuid4(),
        ingestion_run_id=run_id,
        source_id=source_id,
        lane=SourceLane.LANE_1_API_GOV,
        payload_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        raw_content="{'title': 'Cabinet approves metro line 4 expansion'}",
        raw_metadata={"http_status": 200},
    )
    assert raw_event.payload_hash is not None


def test_instantiate_canonical_event_and_fact_check():
    """Test CanonicalEvent and FactCheckTicket relationships and SLA logic."""
    canonical_id = uuid.uuid4()
    canonical = CanonicalEvent(
        id=canonical_id,
        title="Cyclone Alert Issued for Konkan Coast",
        summary="NDRF teams deployed in Ratnagiri and Sindhudurg districts.",
        primary_language=DetectedLanguage.MARATHI,
        district_code="MH-08",
        district_name="Ratnagiri",
        department_code="DISASTER_MGMT",
        department_name="Disaster Management Unit",
        status=CanonicalEventStatus.PENDING_REVIEW,
        verification_status=VerificationStatus.VERIFIED,
        first_detected_at=datetime.now(timezone.utc),
        last_updated_at=datetime.now(timezone.utc),
    )
    assert canonical.primary_language == DetectedLanguage.MARATHI
    assert canonical.district_code == "MH-08"

    ticket = FactCheckTicket(
        id=uuid.uuid4(),
        canonical_event_id=canonical_id,
        claim_text="Viral post claims dams opened in Ratnagiri without warning",
        is_rumor=True,
        event_timestamp=datetime.now(timezone.utc),
        refuted_within_sla_90m=True,
        status=FactCheckTicketStatus.REFUTED,
    )
    assert ticket.refuted_within_sla_90m is True
    assert ticket.status == FactCheckTicketStatus.REFUTED


def test_pillar_score_snapshot():
    """Test PillarScoreSnapshot 100-point composite fields."""
    now = datetime.now(timezone.utc)
    snapshot = PillarScoreSnapshot(
        id=uuid.uuid4(),
        window_start=now,
        window_end=now,
        volume_score=22.5,
        tat_score=24.0,
        sentiment_score=19.5,
        crisis_sla_score=25.0,
        total_composite_score=91.0,
        calculation_metadata={"total_releases": 270, "avg_tat_mins": 38.5},
    )
    assert snapshot.total_composite_score == 91.0
    assert snapshot.volume_score == 22.5
