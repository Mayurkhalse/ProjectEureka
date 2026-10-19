"""Copilot Audit Logger: Append-only persistent tracking for Agent Runs and Tool Calls."""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from eureka.core.database import AsyncSessionLocal
from eureka.models.orm import AgentRun, AgentToolCall, CopilotFeedback

logger = logging.getLogger("eureka.copilot.audit")


def compute_prompt_version_hash(prompt_text: str) -> str:
    """Compute deterministic SHA-256 hash for prompt version tracking."""
    return hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]


async def record_agent_run(
    principal_id: str,
    principal_role: str,
    model_id: str,
    prompt_version_hash: str,
    user_query: str,
    language: str,
    tools_called: List[Dict[str, Any]],
    validation_result: str,
    fallback_used: bool,
    latency_ms: int,
    tool_executions: Optional[List[Dict[str, Any]]] = None,
) -> uuid.UUID:
    """Record an agent run and all its associated tool calls atomically."""
    run_id = uuid.uuid4()
    
    async with AsyncSessionLocal() as session:
        try:
            agent_run = AgentRun(
                id=run_id,
                principal_id=principal_id,
                principal_role=principal_role,
                model_id=model_id,
                prompt_version_hash=prompt_version_hash,
                user_query=user_query,
                language=language,
                tools_called=tools_called,
                validation_result=validation_result,
                fallback_used=fallback_used,
                latency_ms=latency_ms,
                created_at=datetime.now(timezone.utc),
            )
            session.add(agent_run)

            if tool_executions:
                for exec_item in tool_executions:
                    tool_call = AgentToolCall(
                        id=uuid.uuid4(),
                        run_id=run_id,
                        tool_name=exec_item.get("tool_name", "unknown"),
                        tool_args=exec_item.get("tool_args", {}),
                        tool_status=exec_item.get("tool_status", "success"),
                        duration_ms=exec_item.get("duration_ms", 0),
                        created_at=datetime.now(timezone.utc),
                    )
                    session.add(tool_call)

            await session.commit()
            return run_id
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to record agent run audit trail: %s", exc)
            return run_id


async def record_copilot_feedback(
    principal_id: str,
    rating: str,
    run_id: Optional[uuid.UUID] = None,
    reason: Optional[str] = None,
) -> uuid.UUID:
    """Store officer thumbs up/down feedback."""
    feedback_id = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        try:
            feedback = CopilotFeedback(
                id=feedback_id,
                run_id=run_id,
                principal_id=principal_id,
                rating=rating,
                reason=reason,
                created_at=datetime.now(timezone.utc),
            )
            session.add(feedback)
            await session.commit()
            return feedback_id
        except Exception as exc:
            await session.rollback()
            logger.error("Failed to record copilot feedback: %s", exc)
            return feedback_id
