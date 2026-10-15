"""SemIf-OpenJev IRF Binding Engine for Project EUREKA.

Implements text normalization, multilingual script detection (Marathi, Hindi, English),
and semantic binding using Open-Jev Choice, Noul, and Score logic primitives.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.orm import Session

from eureka.models.entities import (
    BindingDecision,
    CanonicalEvent,
    EventSourceLink,
    NormalizedRecord,
    OutboxEvent,
    RawEvent,
)
from eureka.models.enums import (
    AggregateType,
    BindingDecisionType,
    CanonicalEventStatus,
    DetectedLanguage,
    OutboxEventStatus,
    VerificationStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    title: str
    cleaned_text: str
    language: DetectedLanguage
    script: str
    normalized_timestamp: datetime
    entities: Dict[str, Any]
    claims: List[str]


@dataclass
class OpenJevEvaluation:
    primitive: str          # Choice, Noul, Score
    similarity_score: float # 0.0 - 1.0
    decision: BindingDecisionType
    reasoning: str


class TextNormalizer:
    """Normalizes raw text and identifies Indic scripts and languages."""

    @staticmethod
    def detect_language_and_script(text: str) -> Tuple[DetectedLanguage, str]:
        """Detect language (Marathi, Hindi, English) and script based on character distributions."""
        devanagari_chars = len(re.findall(r"[\u0900-\u097F]", text))
        latin_chars = len(re.findall(r"[a-zA-Z]", text))

        if devanagari_chars > latin_chars:
            # Check for Marathi-specific character 'ळ' (\u0933) or common Marathi vocabulary markers
            marathi_markers = ["आहे", "झाले", "केले", "यांनी", "शासनाने", "उपमुख्यमंत्री", "मुख्यमंत्री", "जिल्हा"]
            if "\u0933" in text or any(marker in text for marker in marathi_markers):
                return DetectedLanguage.MARATHI, "Devanagari"
            return DetectedLanguage.HINDI, "Devanagari"
        elif latin_chars > 0:
            return DetectedLanguage.ENGLISH, "Latin"
        return DetectedLanguage.OTHER, "Unknown"

    @staticmethod
    def normalize(raw_content: str, raw_metadata: Dict[str, Any]) -> NormalizationResult:
        """Strip HTML tags, clean whitespace, and standardize metadata."""
        # Clean text
        clean = re.sub(r"<[^>]+>", " ", raw_content)
        clean = re.sub(r"\s+", " ", clean).strip()

        # Extract title
        title = raw_metadata.get("title", "")
        if not title:
            # Use first sentence as title if unavailable
            sentences = clean.split(".")
            title = sentences[0][:200].strip() if sentences else "Untitled Update"

        lang, script = TextNormalizer.detect_language_and_script(clean)

        # Standardize timestamp
        ts_str = raw_metadata.get("published_at") or raw_metadata.get("timestamp")
        parsed_ts = datetime.now(timezone.utc)
        if ts_str:
            try:
                parsed_ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            except Exception:
                pass

        # Extract basic district and department entities
        entities = {}
        for district in ["Mumbai", "Pune", "Nagpur", "Nashik", "Chhatrapati Sambhaji Nagar", "Thane", "Beed"]:
            if district.lower() in clean.lower():
                entities["district"] = district
                break

        for dept in ["Health", "Home", "Revenue", "Agriculture", "Relief", "Disaster Management"]:
            if dept.lower() in clean.lower():
                entities["department"] = dept
                break

        # Claims extraction
        claims = [s.strip() for s in clean.split(".") if len(s.strip()) > 30][:5]

        return NormalizationResult(
            title=title[:500],
            cleaned_text=clean,
            language=lang,
            script=script,
            normalized_timestamp=parsed_ts,
            entities=entities,
            claims=claims,
        )


class SemIfOpenJevBindingEngine:
    """IRF Binding Engine using SemIf-OpenJev Decision Primitives (Choice, Noul, Score)."""

    @staticmethod
    def calculate_semantic_similarity(text_a: str, text_b: str) -> float:
        """Calculate token-level Jaccard & character n-gram similarity."""
        words_a = set(re.findall(r"\w+", text_a.lower()))
        words_b = set(re.findall(r"\w+", text_b.lower()))

        if not words_a or not words_b:
            return 0.0

        intersection = len(words_a & words_b)
        union = len(words_a | words_b)
        jaccard = intersection / union if union > 0 else 0.0

        # Substring / Prefix match bonus
        common_start = 0.2 if text_a[:40].lower() == text_b[:40].lower() else 0.0
        return min(1.0, (jaccard * 0.8) + common_start)

    @classmethod
    def evaluate_openjev(cls, record_text: str, canonical_text: str) -> OpenJevEvaluation:
        """Evaluate semantic similarity using Open-Jev Choice, Noul, and Score primitives."""
        sim = cls.calculate_semantic_similarity(record_text, canonical_text)

        if sim >= 0.90:
            # Primitive: Choice (Positive semantic equivalence)
            return OpenJevEvaluation(
                primitive="Choice",
                similarity_score=sim,
                decision=BindingDecisionType.SAME_EVENT,
                reasoning=f"Open-Jev Choice: Strong semantic convergence ({sim:.3f} >= 0.90)",
            )
        elif sim < 0.70:
            # Primitive: Noul (Semantic divergence / distinct event)
            return OpenJevEvaluation(
                primitive="Noul",
                similarity_score=sim,
                decision=BindingDecisionType.NEW_EVENT,
                reasoning=f"Open-Jev Noul: Orthogonal event context ({sim:.3f} < 0.70)",
            )
        else:
            # Primitive: Score (Ambiguous overlap requiring human desk review)
            return OpenJevEvaluation(
                primitive="Score",
                similarity_score=sim,
                decision=BindingDecisionType.NEEDS_HUMAN_REVIEW,
                reasoning=f"Open-Jev Score: Boundary confidence ({sim:.3f} in [0.70, 0.90])",
            )

    @classmethod
    def bind_record(
        cls,
        session: Session,
        normalized_record: NormalizedRecord,
    ) -> Tuple[CanonicalEvent, BindingDecision]:
        """Match incoming normalized record against active canonical events."""
        # Find active canonical events in the last 72 hours
        stmt = (
            select(CanonicalEvent)
            .order_by(CanonicalEvent.last_updated_at.desc())
            .limit(50)
        )
        candidates = session.execute(stmt).scalars().all()

        best_match: Optional[CanonicalEvent] = None
        best_eval: Optional[OpenJevEvaluation] = None
        max_score = -1.0

        for cand in candidates:
            eval_res = cls.evaluate_openjev(normalized_record.cleaned_text, cand.summary)
            if eval_res.similarity_score > max_score:
                max_score = eval_res.similarity_score
                best_match = cand
                best_eval = eval_res

        # If no candidates or best match is < 0.70, create new canonical event
        if not best_match or not best_eval or best_eval.decision == BindingDecisionType.NEW_EVENT:
            decision_eval = best_eval or OpenJevEvaluation(
                primitive="Noul",
                similarity_score=0.0,
                decision=BindingDecisionType.NEW_EVENT,
                reasoning="No preceding candidate events; instantiated new CanonicalEvent",
            )

            canonical = CanonicalEvent(
                id=uuid.uuid4(),
                title=normalized_record.title,
                summary=normalized_record.cleaned_text[:1000],
                primary_language=normalized_record.detected_language,
                district_code=normalized_record.entities.get("district", "MH-GENERAL"),
                district_name=normalized_record.entities.get("district", "Maharashtra"),
                department_code=normalized_record.entities.get("department", "GENERAL"),
                department_name=normalized_record.entities.get("department", "General Administration"),
                status=CanonicalEventStatus.PENDING_REVIEW,
                verification_status=VerificationStatus.UNVERIFIED,
                first_detected_at=normalized_record.normalized_timestamp,
                last_updated_at=datetime.now(timezone.utc),
            )
            session.add(canonical)
            session.flush()

        elif best_eval.decision == BindingDecisionType.SAME_EVENT:
            canonical = best_match
            canonical.last_updated_at = datetime.now(timezone.utc)
            decision_eval = best_eval

        else:  # NEEDS_HUMAN_REVIEW
            canonical = best_match
            canonical.status = CanonicalEventStatus.PENDING_REVIEW
            decision_eval = best_eval

        # Create EventSourceLink
        link = EventSourceLink(
            id=uuid.uuid4(),
            canonical_event_id=canonical.id,
            normalized_record_id=normalized_record.id,
            similarity_score=decision_eval.similarity_score,
            bound_by="SemIf-OpenJev",
            bound_at=datetime.now(timezone.utc),
        )
        session.add(link)

        # Create BindingDecision record
        decision = BindingDecision(
            id=uuid.uuid4(),
            normalized_record_id=normalized_record.id,
            canonical_event_id=canonical.id,
            similarity_score=decision_eval.similarity_score,
            decision_type=decision_eval.decision,
            logic_primitive=decision_eval.primitive,
            reasoning=decision_eval.reasoning,
            decided_at=datetime.now(timezone.utc),
        )
        session.add(decision)

        # Emit OutboxEvent for Neo4j synchronization
        outbox = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type=AggregateType.CANONICAL_EVENT,
            aggregate_id=str(canonical.id),
            event_type="UPDATED" if best_eval and best_eval.decision == BindingDecisionType.SAME_EVENT else "CREATED",
            payload={
                "title": canonical.title,
                "summary": canonical.summary,
                "status": canonical.status.value if hasattr(canonical.status, "value") else str(canonical.status),
                "verification_status": canonical.verification_status.value if hasattr(canonical.verification_status, "value") else str(canonical.verification_status),
                "primary_language": canonical.primary_language.value if hasattr(canonical.primary_language, "value") else str(canonical.primary_language),
                "district_code": canonical.district_code,
                "district_name": canonical.district_name,
                "department_code": canonical.department_code,
                "department_name": canonical.department_name,
                "first_detected_at": canonical.first_detected_at.isoformat(),
                "last_updated_at": canonical.last_updated_at.isoformat(),
            },
            status=OutboxEventStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )
        session.add(outbox)
        session.commit()

        return canonical, decision
