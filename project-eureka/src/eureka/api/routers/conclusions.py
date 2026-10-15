"""Human Review Workflow & State Machine Endpoints.

Valid states: draft -> pending_review -> approved | overridden | rejected.
Automated outputs remain pending_review until explicitly authorized by a user role.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from eureka.api.auth import TokenData, require_roles
from eureka.core.database import get_async_db
from eureka.models.entities import CanonicalEvent, HumanReviewAction, OutboxEvent
from eureka.models.enums import (
    AggregateType,
    CanonicalEventStatus,
    OutboxEventStatus,
    UserRole,
    VerificationStatus,
)

router = APIRouter(prefix="/api/v1/conclusions", tags=["Conclusion & Review State Machine"])


class ReviewActionRequest(BaseModel):
    action: str  # APPROVE, OVERRIDE, REJECT, SUBMIT_FOR_REVIEW
    target_state: CanonicalEventStatus
    verification_status: Optional[VerificationStatus] = None
    comments: Optional[str] = None


VALID_TRANSITIONS = {
    CanonicalEventStatus.DRAFT: [CanonicalEventStatus.PENDING_REVIEW],
    CanonicalEventStatus.PENDING_REVIEW: [
        CanonicalEventStatus.APPROVED,
        CanonicalEventStatus.OVERRIDDEN,
        CanonicalEventStatus.REJECTED,
    ],
    CanonicalEventStatus.APPROVED: [CanonicalEventStatus.OVERRIDDEN],
    CanonicalEventStatus.OVERRIDDEN: [CanonicalEventStatus.APPROVED, CanonicalEventStatus.REJECTED],
    CanonicalEventStatus.REJECTED: [CanonicalEventStatus.PENDING_REVIEW],
}


@router.get("/")
async def list_conclusions(
    status_filter: Optional[CanonicalEventStatus] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db),
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK])),
):
    """Retrieve canonical events with state machine and sentiment indicators."""
    stmt = select(CanonicalEvent).order_by(CanonicalEvent.last_updated_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(CanonicalEvent.status == status_filter)

    result = await db.execute(stmt)
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "title": e.title,
            "summary": e.summary,
            "status": e.status,
            "verification_status": e.verification_status,
            "primary_language": e.primary_language,
            "district_code": e.district_code,
            "district_name": e.district_name,
            "department_code": e.department_code,
            "department_name": e.department_name,
            "sentiment_label": e.sentiment_label,
            "sentiment_score": e.sentiment_score,
            "first_detected_at": e.first_detected_at.isoformat(),
            "last_updated_at": e.last_updated_at.isoformat(),
        }
        for e in events
    ]


@router.post("/{event_id}/review")
async def execute_review_action(
    event_id: uuid.UUID,
    payload: ReviewActionRequest,
    db: AsyncSession = Depends(get_async_db),
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DISTRICT_COLLECTOR, UserRole.DIO_DESK])),
):
    """Execute state machine transition on a canonical conclusion with RBAC authorization."""
    event = await db.get(CanonicalEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Canonical event conclusion not found")

    # If user is District Collector, restrict to their assigned district
    if user.role == UserRole.DISTRICT_COLLECTOR and user.district_code:
        if event.district_code and event.district_code != user.district_code:
            raise HTTPException(
                status_code=403,
                detail=f"District Collector scope restricted to district '{user.district_code}'",
            )

    current_state = event.status
    allowed_states = VALID_TRANSITIONS.get(current_state, [])

    if payload.target_state not in allowed_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid state transition from '{current_state.value if hasattr(current_state, 'value') else current_state}' "
                f"to '{payload.target_state.value if hasattr(payload.target_state, 'value') else payload.target_state}'. "
                f"Allowed target states: {[s.value if hasattr(s, 'value') else str(s) for s in allowed_states]}"
            ),
        )

    if payload.target_state == CanonicalEventStatus.OVERRIDDEN and not payload.comments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Comments / justification required when overriding automated intelligence.",
        )

    # Apply state transition
    event.status = payload.target_state
    if payload.verification_status:
        event.verification_status = payload.verification_status
    event.last_updated_at = datetime.now(timezone.utc)

    # Record immutable audit action in human_review_actions
    audit_action = HumanReviewAction(
        id=uuid.uuid4(),
        entity_type="CanonicalEvent",
        entity_id=event.id,
        reviewer_id=user.username,
        role=user.role,
        previous_state=current_state.value if hasattr(current_state, "value") else str(current_state),
        new_state=payload.target_state.value if hasattr(payload.target_state, "value") else str(payload.target_state),
        action_taken=payload.action,
        comments=payload.comments,
        created_at=datetime.now(timezone.utc),
    )
    db.add(audit_action)

    # Emit OutboxEvent for Neo4j update
    outbox = OutboxEvent(
        id=uuid.uuid4(),
        aggregate_type=AggregateType.CANONICAL_EVENT,
        aggregate_id=str(event.id),
        event_type="STATE_CHANGED",
        payload={
            "title": event.title,
            "summary": event.summary,
            "status": event.status.value if hasattr(event.status, "value") else str(event.status),
            "verification_status": event.verification_status.value if hasattr(event.verification_status, "value") else str(event.verification_status),
            "reviewer_id": user.username,
            "role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "last_updated_at": event.last_updated_at.isoformat(),
        },
        status=OutboxEventStatus.PENDING,
        created_at=datetime.now(timezone.utc),
    )
    db.add(outbox)
    await db.commit()

    return {
        "status": "success",
        "event_id": str(event.id),
        "previous_state": audit_action.previous_state,
        "new_state": audit_action.new_state,
        "action_taken": audit_action.action_taken,
        "reviewed_by": user.username,
        "role": user.role,
    }
