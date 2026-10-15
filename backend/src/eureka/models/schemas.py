"""Pydantic v2 schemas for API requests, responses, and token validation."""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from eureka.models.enums import (
    CanonicalEventStatus,
    DetectedLanguage,
    SourceLane,
    UserRole,
    VerificationStatus,
)


class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TokenData(BaseSchema):
    username: str
    role: UserRole
    district_code: Optional[str] = None


class DevTokenRequest(BaseSchema):
    username: str
    role: UserRole
    district_code: Optional[str] = None


class SourceRegistryCreate(BaseSchema):
    name: str
    lane: SourceLane
    base_url: str
    config_json: Dict[str, Any] = Field(default_factory=dict)
    poll_interval_sec: int = 300


class SourceRegistryRead(BaseSchema):
    id: uuid.UUID
    name: str
    lane: SourceLane
    base_url: str
    config_json: Dict[str, Any]
    is_active: bool
    poll_interval_sec: int
    last_polled_at: Optional[datetime] = None
    created_at: datetime


class CSVImportRequest(BaseSchema):
    csv_file: str  # e.g., "press_releases.csv", "media_clippings.csv"
    lane: SourceLane = SourceLane.LANE_1_API_GOV
    source_name: Optional[str] = None


class ReviewActionRequest(BaseSchema):
    action: str  # APPROVE, OVERRIDE, REJECT
    target_state: CanonicalEventStatus
    verification_status: Optional[VerificationStatus] = None
    comments: Optional[str] = None


class CanonicalEventRead(BaseSchema):
    id: uuid.UUID
    title: str
    summary: str
    primary_language: DetectedLanguage
    district_code: Optional[str] = None
    district_name: Optional[str] = None
    department_code: Optional[str] = None
    department_name: Optional[str] = None
    status: CanonicalEventStatus
    verification_status: VerificationStatus
    sentiment_label: Optional[str] = None
    sentiment_score: Optional[float] = None
    first_detected_at: datetime
    last_updated_at: datetime


class PillarScoreRead(BaseSchema):
    id: uuid.UUID
    district_id: Optional[int] = None
    district_name: Optional[str] = None
    volume_score: float
    tat_score: float
    sentiment_score: float
    crisis_sla_score: float
    total_composite_score: float
    window_start: datetime
    window_end: datetime
    calculation_metadata: Dict[str, Any]
    created_at: datetime
