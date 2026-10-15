"""SQLAlchemy 2.0 ORM models for Project EUREKA database."""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from eureka.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from eureka.models.enums import (
    AggregateType,
    BindingDecisionType,
    CanonicalEventStatus,
    DetectedLanguage,
    FactCheckTicketStatus,
    IngestionRunStatus,
    OutboxEventStatus,
    SourceLane,
    UserRole,
    VerificationStatus,
)


class SourceRegistry(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Registry of ingestion sources across QUAD lanes."""

    __tablename__ = "source_registry"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    lane: Mapped[SourceLane] = mapped_column(String(50), nullable=False, index=True)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    config_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    poll_interval_sec: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    last_polled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    ingestion_runs: Mapped[List["IngestionRun"]] = relationship("IngestionRun", back_populates="source", cascade="all, delete-orphan")
    raw_events: Mapped[List["RawEvent"]] = relationship("RawEvent", back_populates="source", cascade="all, delete-orphan")


class IngestionRun(Base, UUIDPrimaryKeyMixin):
    """Tracks batch execution lifecycle for an ingestion source."""

    __tablename__ = "ingestion_runs"

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_registry.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[IngestionRunStatus] = mapped_column(String(50), default=IngestionRunStatus.STARTED, nullable=False, index=True)
    items_ingested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_log: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    source: Mapped["SourceRegistry"] = relationship("SourceRegistry", back_populates="ingestion_runs")
    raw_events: Mapped[List["RawEvent"]] = relationship("RawEvent", back_populates="ingestion_run", cascade="all, delete-orphan")


class RawEvent(Base, UUIDPrimaryKeyMixin):
    """Immutable raw event payloads ingested from APIs or CSVAdapter before normalization."""

    __tablename__ = "raw_events"

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ingestion_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("source_registry.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lane: Mapped[SourceLane] = mapped_column(String(50), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA-256
    raw_content: Mapped[str] = mapped_column(Text, nullable=False)
    raw_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    # Relationships
    source: Mapped["SourceRegistry"] = relationship("SourceRegistry", back_populates="raw_events")
    ingestion_run: Mapped["IngestionRun"] = relationship("IngestionRun", back_populates="raw_events")
    normalized_record: Mapped[Optional["NormalizedRecord"]] = relationship(
        "NormalizedRecord", back_populates="raw_event", uselist=False, cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_raw_events_source_hash", "source_id", "payload_hash", unique=True),
    )


class NormalizedRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Standardized record extracted from raw content with language detection and clean timestamps."""

    __tablename__ = "normalized_records"

    raw_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("raw_events.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[DetectedLanguage] = mapped_column(String(20), default=DetectedLanguage.OTHER, nullable=False, index=True)
    script: Mapped[str] = mapped_column(String(50), default="Unknown", nullable=False)
    normalized_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    entities: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    claims: Mapped[List[str]] = mapped_column(JSONB, default=list, nullable=False)

    # Relationships
    raw_event: Mapped["RawEvent"] = relationship("RawEvent", back_populates="normalized_record")
    event_source_links: Mapped[List["EventSourceLink"]] = relationship("EventSourceLink", back_populates="normalized_record")
    binding_decisions: Mapped[List["BindingDecision"]] = relationship("BindingDecision", back_populates="normalized_record")


class CanonicalEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Authoritative clustered event entity bound by IRF SemIf-OpenJev."""

    __tablename__ = "canonical_events"

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    primary_language: Mapped[DetectedLanguage] = mapped_column(String(20), default=DetectedLanguage.MARATHI, nullable=False)
    district_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    district_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    department_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    department_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[CanonicalEventStatus] = mapped_column(
        String(50), default=CanonicalEventStatus.PENDING_REVIEW, nullable=False, index=True
    )
    verification_status: Mapped[VerificationStatus] = mapped_column(
        String(50), default=VerificationStatus.UNVERIFIED, nullable=False, index=True
    )
    sentiment_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    source_links: Mapped[List["EventSourceLink"]] = relationship("EventSourceLink", back_populates="canonical_event", cascade="all, delete-orphan")
    fact_check_tickets: Mapped[List["FactCheckTicket"]] = relationship("FactCheckTicket", back_populates="canonical_event", cascade="all, delete-orphan")
    binding_decisions: Mapped[List["BindingDecision"]] = relationship("BindingDecision", back_populates="canonical_event")


class EventSourceLink(Base, UUIDPrimaryKeyMixin):
    """Many-to-one mapping linking normalized source records to canonical events."""

    __tablename__ = "event_source_links"

    canonical_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    normalized_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    bound_by: Mapped[str] = mapped_column(String(100), default="SemIf-OpenJev", nullable=False)
    bound_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    canonical_event: Mapped["CanonicalEvent"] = relationship("CanonicalEvent", back_populates="source_links")
    normalized_record: Mapped["NormalizedRecord"] = relationship("NormalizedRecord", back_populates="event_source_links")

    __table_args__ = (
        Index("ix_event_source_unique", "canonical_event_id", "normalized_record_id", unique=True),
    )


class BindingDecision(Base, UUIDPrimaryKeyMixin):
    """Persistent audit record of SemIf-OpenJev binding comparisons."""

    __tablename__ = "binding_decisions"

    normalized_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("normalized_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canonical_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_events.id", ondelete="SET NULL"), nullable=True, index=True
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    decision_type: Mapped[BindingDecisionType] = mapped_column(String(50), nullable=False, index=True)
    logic_primitive: Mapped[str] = mapped_column(String(50), nullable=False)  # Choice, Noul, Score
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )

    # Relationships
    normalized_record: Mapped["NormalizedRecord"] = relationship("NormalizedRecord", back_populates="binding_decisions")
    canonical_event: Mapped[Optional["CanonicalEvent"]] = relationship("CanonicalEvent", back_populates="binding_decisions")


class FactCheckTicket(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tracks rumor claims, refutations, and the 90-minute crisis SLA."""

    __tablename__ = "fact_check_tickets"

    canonical_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_text: Mapped[str] = mapped_column(Text, nullable=False)
    is_rumor: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    refuted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    refuted_within_sla_90m: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    status: Mapped[FactCheckTicketStatus] = mapped_column(
        String(50), default=FactCheckTicketStatus.OPEN, nullable=False, index=True
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    canonical_event: Mapped["CanonicalEvent"] = relationship("CanonicalEvent", back_populates="fact_check_tickets")


class PillarScoreSnapshot(Base, UUIDPrimaryKeyMixin):
    """Periodic snapshots of the 100-Point Composite Index across all 4 pillars."""

    __tablename__ = "pillar_score_snapshots"

    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    district_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    district_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    volume_score: Mapped[float] = mapped_column(Float, nullable=False)         # 0-25
    tat_score: Mapped[float] = mapped_column(Float, nullable=False)            # 0-25
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)      # 0-25
    crisis_sla_score: Mapped[float] = mapped_column(Float, nullable=False)     # 0-25
    total_composite_score: Mapped[float] = mapped_column(Float, nullable=False) # 0-100
    calculation_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )


class HumanReviewAction(Base, UUIDPrimaryKeyMixin):
    """Immutable audit log for human approvals, overrides, and rejections."""

    __tablename__ = "human_review_actions"

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    reviewer_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(50), nullable=False, index=True)
    previous_state: Mapped[str] = mapped_column(String(50), nullable=False)
    new_state: Mapped[str] = mapped_column(String(50), nullable=False)
    action_taken: Mapped[str] = mapped_column(String(50), nullable=False)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )


class OutboxEvent(Base, UUIDPrimaryKeyMixin):
    """Transactional Outbox table for reliable CDC projection into Neo4j."""

    __tablename__ = "outbox_events"

    aggregate_type: Mapped[AggregateType] = mapped_column(String(50), nullable=False, index=True)
    aggregate_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # CREATED, UPDATED, DELETED, LINKED
    payload: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[OutboxEventStatus] = mapped_column(
        String(50), default=OutboxEventStatus.PENDING, nullable=False, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_outbox_events_status_created", "status", "created_at"),
    )
