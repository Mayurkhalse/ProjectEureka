"""CSV Adapter for Project EUREKA QUAD Ingestion Subsystem.

Bridges the zero-API-key status by ingesting local benchmark data directly into
the `raw_events` table with deterministic SHA-256 provenance hashing and validation.
"""

import csv
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session

from eureka.models.orm import RawEvent, SourceRegistry
from eureka.models.enums import SourceLane
from eureka.quad_ingestion.base import BaseIngestionAdapter, compute_payload_hash

logger = logging.getLogger(__name__)


class CSVAdapter(BaseIngestionAdapter):
    """Adapter reading local CSV test datasets and persisting raw events."""

    def __init__(self, seed_dir: Optional[str] = None):
        if seed_dir:
            self.seed_dir = Path(seed_dir)
        else:
            # Locate seed_data relative to project root or current working dir
            candidate_paths = [
                Path("backend/seed_data"),
                Path("project-eureka/seed_data"),
                Path("seed_data"),
                Path(__file__).resolve().parent.parent.parent.parent / "seed_data",
                Path(__file__).resolve().parent.parent.parent.parent / "Maha_Command_Center_Student_Pack" / "Maha_Command_Center_Student_Pack" / "2_Seed_Data",
            ]
            self.seed_dir = next((p for p in candidate_paths if p.exists()), Path("backend/seed_data") if Path("backend/seed_data").exists() else Path("seed_data"))

    def resolve_file_path(self, filename_or_path: str) -> Path:
        """Resolve full path to CSV file."""
        p = Path(filename_or_path)
        if p.is_file():
            return p
        seed_path = self.seed_dir / filename_or_path
        if seed_path.is_file():
            return seed_path
        # Search filename within seed directory
        for item in self.seed_dir.glob("*.csv"):
            if item.name.lower() == filename_or_path.lower():
                return item
        raise FileNotFoundError(f"CSV file not found: {filename_or_path} (searched in {self.seed_dir})")

    def validate_press_release(self, row: Dict[str, str]) -> Tuple[bool, str]:
        """Validate temporal ordering of event vs publication.
        
        Rejects records published before the event occurrence (e.g., invalid_press_releases.csv).
        """
        event_ts_str = row.get("event_timestamp")
        pub_ts_str = row.get("published_timestamp")

        if event_ts_str and pub_ts_str:
            try:
                event_ts = datetime.fromisoformat(event_ts_str.replace("Z", "+00:00"))
                pub_ts = datetime.fromisoformat(pub_ts_str.replace("Z", "+00:00"))
                if pub_ts < event_ts:
                    return False, f"Invalid temporal sequence: published ({pub_ts_str}) before event ({event_ts_str})"
            except Exception as exc:
                return False, f"Timestamp parsing failure: {exc}"
        return True, ""

    def ingest_source(
        self,
        session: Session,
        source: SourceRegistry,
        ingestion_run_id: uuid.UUID,
    ) -> List[RawEvent]:
        """Ingest source records specified by source.config_json['csv_file'] or source.base_url."""
        config = source.config_json or {}
        target_file = config.get("csv_file") or source.base_url
        csv_path = self.resolve_file_path(target_file)
        limit = config.get("limit")

        logger.info("CSVAdapter: Ingesting source '%s' from %s", source.name, csv_path)
        return self.ingest_file(
            session=session,
            file_path=csv_path,
            lane=source.lane,
            source_id=source.id,
            ingestion_run_id=ingestion_run_id,
            limit=limit,
        )

    def ingest_file(
        self,
        session: Session,
        file_path: Path,
        lane: SourceLane,
        source_id: uuid.UUID,
        ingestion_run_id: uuid.UUID,
        limit: Optional[int] = None,
    ) -> List[RawEvent]:
        """Read CSV, validate records, compute SHA-256 hashes, and write directly to raw_events."""
        raw_events: List[RawEvent] = []
        rejected_count = 0

        with open(file_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                if limit and idx >= limit:
                    break

                # Validate press releases
                if "event_timestamp" in row and "published_timestamp" in row:
                    is_valid, reason = self.validate_press_release(row)
                    if not is_valid:
                        logger.warning("Rejected row %d from %s: %s", idx, file_path.name, reason)
                        rejected_count += 1
                        continue

                # Prepare raw JSON representation preserving raw fields
                raw_payload = json.dumps(row, ensure_ascii=False)
                metadata = {
                    "source_file": file_path.name,
                    "row_index": idx,
                    "lane": lane.value if hasattr(lane, "value") else str(lane),
                    "adapter": "CSVAdapter",
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }

                payload_hash = compute_payload_hash(raw_payload)

                raw_event = RawEvent(
                    id=uuid.uuid4(),
                    ingestion_run_id=ingestion_run_id,
                    source_id=source_id,
                    lane=lane,
                    payload_hash=payload_hash,
                    raw_content=raw_payload,
                    raw_metadata=metadata,
                    ingested_at=datetime.now(timezone.utc),
                )
                session.add(raw_event)
                raw_events.append(raw_event)

        session.flush()
        logger.info(
            "CSVAdapter ingested %d valid records (%d rejected) from %s",
            len(raw_events),
            rejected_count,
            file_path.name,
        )
        return raw_events


# Type alias helper
Tuple_Bool_Str = tuple[bool, str]
