"""QUAD Ingestion: API Connectors for Lanes 1 and 2 (Government & Departmental Portals).

Provides resilient HTTP clients using httpx with dynamic source_registry configs,
exponential retries, SHA-256 payload hashing, and direct raw_events write-back.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from eureka.models.entities import RawEvent, SourceRegistry
from eureka.models.enums import SourceLane

logger = logging.getLogger(__name__)


def compute_payload_hash(content: str) -> str:
    """Compute deterministic SHA-256 hash of raw content for provenance and deduplication."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class BaseApiConnector:
    """Base API connector handling HTTP transport, retries, and persistence."""

    def __init__(self, timeout_sec: float = 30.0):
        self.timeout_sec = timeout_sec

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        reraise=True,
    )
    def fetch_json(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute synchronous HTTP GET request with retries and return JSON data."""
        request_headers = {"User-Agent": "Project-EUREKA-MahaCommandCenter/1.0", "Accept": "application/json"}
        if headers:
            request_headers.update(headers)

        with httpx.Client(timeout=self.timeout_sec, follow_redirects=True) as client:
            response = client.get(url, headers=request_headers, params=params)
            response.raise_for_status()
            return response.json()

    def persist_raw_event(
        self,
        session: Session,
        ingestion_run_id: uuid.UUID,
        source: SourceRegistry,
        raw_content: str,
        raw_metadata: Dict[str, Any],
    ) -> RawEvent:
        """Write raw payload directly to raw_events table preserving provenance."""
        payload_hash = compute_payload_hash(raw_content)

        raw_event = RawEvent(
            id=uuid.uuid4(),
            ingestion_run_id=ingestion_run_id,
            source_id=source.id,
            lane=source.lane,
            payload_hash=payload_hash,
            raw_content=raw_content,
            raw_metadata=raw_metadata,
            ingested_at=datetime.now(timezone.utc),
        )
        session.add(raw_event)
        session.flush()
        return raw_event


class GovApiConnector(BaseApiConnector):
    """Lane 1 Connector: Government structured Open Data APIs (data.gov.in, pib.gov.in)."""

    def ingest_source(
        self,
        session: Session,
        source: SourceRegistry,
        ingestion_run_id: uuid.UUID,
    ) -> List[RawEvent]:
        """Fetch records from government API and write raw payloads directly to DB."""
        config = source.config_json or {}
        headers = config.get("headers", {})
        params = config.get("params", {})
        records_key = config.get("records_key", "records")

        logger.info("Lane 1: Ingesting gov source '%s' from %s", source.name, source.base_url)
        data = self.fetch_json(source.base_url, headers=headers, params=params)

        raw_events: List[RawEvent] = []
        items = data.get(records_key, [data]) if isinstance(data, dict) else data

        if not isinstance(items, list):
            items = [items]

        for idx, item in enumerate(items):
            raw_str = json.dumps(item, ensure_ascii=False)
            metadata = {
                "source_url": source.base_url,
                "lane": SourceLane.LANE_1_API_GOV,
                "item_index": idx,
                "ingested_via": "GovApiConnector",
            }
            raw_event = self.persist_raw_event(session, ingestion_run_id, source, raw_str, metadata)
            raw_events.append(raw_event)

        logger.info("Lane 1: Ingested %d raw events from '%s'", len(raw_events), source.name)
        return raw_events


class PortalApiConnector(BaseApiConnector):
    """Lane 2 Connector: Official Department Portals (DGIPR, Relief, Home, Health)."""

    def ingest_source(
        self,
        session: Session,
        source: SourceRegistry,
        ingestion_run_id: uuid.UUID,
    ) -> List[RawEvent]:
        """Fetch departmental press releases and updates and write raw payloads to DB."""
        config = source.config_json or {}
        headers = config.get("headers", {})
        params = config.get("params", {})
        items_path = config.get("items_path", "data")

        logger.info("Lane 2: Ingesting portal source '%s' from %s", source.name, source.base_url)
        data = self.fetch_json(source.base_url, headers=headers, params=params)

        raw_events: List[RawEvent] = []
        items = data.get(items_path, [data]) if isinstance(data, dict) else data

        if not isinstance(items, list):
            items = [items]

        for idx, item in enumerate(items):
            raw_str = json.dumps(item, ensure_ascii=False)
            metadata = {
                "source_url": source.base_url,
                "lane": SourceLane.LANE_2_API_PORTAL,
                "item_index": idx,
                "department": config.get("department", "GENERAL"),
                "ingested_via": "PortalApiConnector",
            }
            raw_event = self.persist_raw_event(session, ingestion_run_id, source, raw_str, metadata)
            raw_events.append(raw_event)

        logger.info("Lane 2: Ingested %d raw events from '%s'", len(raw_events), source.name)
        return raw_events
