"""Base Ingestion Adapter Interface for Project EUREKA QUAD Ingestion Mesh."""

import abc
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List
from sqlalchemy.orm import Session

from eureka.models.orm import RawEvent, SourceRegistry
from eureka.models.enums import SourceLane


def compute_payload_hash(content: str) -> str:
    """Compute deterministic SHA-256 hash of raw content for provenance and deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class BaseIngestionAdapter(abc.ABC):
    """Abstract base adapter for QUAD ingestion lanes (APIs, Web Scrapers, and CSV Adapters)."""

    @abc.abstractmethod
    def ingest_source(
        self,
        session: Session,
        source: SourceRegistry,
        ingestion_run_id: uuid.UUID,
    ) -> List[RawEvent]:
        """Ingest source records and write directly to raw_events table."""
        pass

    def persist_raw_event(
        self,
        session: Session,
        ingestion_run_id: uuid.UUID,
        source_id: uuid.UUID,
        lane: SourceLane,
        raw_content: str,
        raw_metadata: Dict[str, Any],
    ) -> RawEvent:
        """Write raw payload directly to raw_events table preserving provenance."""
        payload_hash = compute_payload_hash(raw_content)

        raw_event = RawEvent(
            id=uuid.uuid4(),
            ingestion_run_id=ingestion_run_id,
            source_id=source_id,
            lane=lane,
            payload_hash=payload_hash,
            raw_content=raw_content,
            raw_metadata=raw_metadata,
            ingested_at=datetime.now(timezone.utc),
        )
        session.add(raw_event)
        session.flush()
        return raw_event
