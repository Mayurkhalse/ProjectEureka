"""FastAPI Router for Open UI Copilot.

Provides:
- POST /api/v1/copilot/query: SSE streaming endpoint rendering progressive OpenUI Lang
- POST /api/v1/copilot/feedback: Officer feedback collection
- GET /api/v1/copilot/memory: Retrieve officer's own presentation preferences
- DELETE /api/v1/copilot/memory/{id}: Delete a specific preference
- DELETE /api/v1/copilot/memory: Purge all officer preferences ('Forget Me')
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from eureka.api.auth import TokenData, get_current_user
from eureka.copilot.audit import compute_prompt_version_hash, record_agent_run, record_copilot_feedback
from eureka.copilot.config import get_copilot_settings
from eureka.copilot.gemma_client import GemmaClient
from eureka.copilot.memory import get_memory_manager
from eureka.copilot.openui_generator import (
    detect_language,
    generate_copilot_system_instruction,
    validate_openui_output,
)
from eureka.copilot.tools import (
    COPILOT_TOOLS_MAP,
    CopilotPrincipal,
    get_copilot_function_declarations,
    tool_league_table,
    LeagueTableArgs,
)
from eureka.copilot.viewspec import ViewSpec, ViewSpecBuilder

logger = logging.getLogger("eureka.copilot.router")

router = APIRouter(prefix="/api/v1/copilot", tags=["Open UI Copilot"])

# Global client singleton
_gemma_client = GemmaClient()


class CopilotQueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000, description="Officer query in Marathi, Hindi, or English")
    language: Optional[str] = Field(default="auto", description="Language hint: mr, hi, en, or auto")


class CopilotFeedbackRequest(BaseModel):
    run_id: Optional[uuid.UUID] = Field(default=None, description="Agent run ID being evaluated")
    rating: str = Field(description="thumbs_up or thumbs_down")
    reason: Optional[str] = Field(default=None, description="Optional text feedback")


@router.post("/query", summary="Execute Open UI Copilot Query with SSE Streaming")
async def copilot_query(
    payload: CopilotQueryRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Execute governed data copilot query returning an SSE stream of OpenUI Lang."""
    settings = get_copilot_settings()
    if not settings.COPILOT_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Open UI Copilot is disabled on this instance (COPILOT_ENABLED=false).",
        )

    principal = CopilotPrincipal(
        username=current_user.username,
        role=current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        district_code=current_user.district_code,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        start_time = time.time()
        user_query = payload.query.strip()
        lang = payload.language if payload.language in ("mr", "hi", "en") else detect_language(user_query)

        # 1. Yield Initial Status
        yield f"event: status\ndata: {json.dumps({'step': 'init', 'message': 'Processing query...', 'language': lang})}\n\n"

        # 2. Retrieve Mem0 Preferences (Bounded 800ms fail-open)
        mem_mgr = get_memory_manager()
        preferences = await mem_mgr.search_preferences(principal.username, user_query)
        if preferences:
            yield f"event: status\ndata: {json.dumps({'step': 'memory', 'message': f'Retrieved {len(preferences)} presentation preference(s).'})}\n\n"

        # 3. Model & Function Calling Flow
        sys_prompt = generate_copilot_system_instruction(language=lang, user_preferences=preferences)
        prompt_hash = compute_prompt_version_hash(sys_prompt)

        tool_declarations = [{"functionDeclarations": get_copilot_function_declarations()}]
        contents = [{"role": "user", "parts": [{"text": user_query}]}]

        executed_tools_data: List[Dict[str, Any]] = []
        executed_tool_calls_audit: List[Dict[str, Any]] = []
        tools_called_names: List[str] = []

        validation_result = "valid"
        fallback_used = False
        final_markup = ""
        final_view_spec = None

        try:
            # First turn: Ask model for tool calls
            yield f"event: status\ndata: {json.dumps({'step': 'analyzing', 'message': 'Consulting DGIPR analytical data services...'})}\n\n"

            turn_count = 0
            max_turns = 4

            while turn_count < max_turns:
                turn_count += 1
                response = await _gemma_client.generate(
                    contents=contents,
                    system_instruction=sys_prompt,
                    tools=tool_declarations,
                    user_id=principal.username,
                )

                candidates = response.get("candidates", [])
                if not candidates:
                    break

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    break

                # Check for function call in ANY part
                fn_part = next((p for p in parts if "functionCall" in p), None)
                if fn_part:
                    fn_call = fn_part["functionCall"]
                    fn_name = fn_call.get("name")
                    fn_args = fn_call.get("args", {})
                    tools_called_names.append(fn_name)

                    yield f"event: status\ndata: {json.dumps({'step': 'tool_call', 'tool': fn_name, 'args': fn_args})}\n\n"

                    # Execute governed tool
                    t0 = time.time()
                    tool_def = COPILOT_TOOLS_MAP.get(fn_name)
                    if tool_def:
                        arg_model, fn_impl = tool_def
                        try:
                            parsed_args = arg_model(**fn_args)
                            tool_out = fn_impl(principal, parsed_args)
                            tool_status = "success"
                        except Exception as t_err:
                            tool_out = {"error": "EXECUTION_ERROR", "message": str(t_err), "source_status": "unavailable"}
                            tool_status = "error"
                    else:
                        tool_out = {"error": "UNKNOWN_TOOL", "message": f"Tool '{fn_name}' does not exist.", "source_status": "unavailable"}
                        tool_status = "error"

                    duration_ms = int((time.time() - t0) * 1000)
                    executed_tools_data.append(tool_out)
                    executed_tool_calls_audit.append({
                        "tool_name": fn_name,
                        "tool_args": fn_args,
                        "tool_status": tool_status,
                        "duration_ms": duration_ms,
                    })

                    # Append to conversation
                    contents.append({
                        "role": "model",
                        "parts": parts,
                    })
                    contents.append({
                        "role": "function",
                        "parts": [{
                            "functionResponse": {
                                "name": fn_name,
                                "response": tool_out,
                            }
                        }],
                    })
                    continue

                # If no function call, check for non-thought text output
                text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought", False)]
                if not text_parts:
                    text_parts = [p["text"] for p in parts if "text" in p]

                if text_parts:
                    final_markup = "\n".join(text_parts).strip()
                    break

            # If no tools were called, default to league_table query scoped to caller
            if not executed_tools_data:
                default_res = tool_league_table(principal, LeagueTableArgs())
                executed_tools_data.append(default_res)
                executed_tool_calls_audit.append({
                    "tool_name": "league_table",
                    "tool_args": {},
                    "tool_status": "success",
                    "duration_ms": 10,
                })
                tools_called_names.append("league_table")

            # 4. Validate Generated OpenUI Lang
            is_valid, val_errors = validate_openui_output(final_markup, executed_tools_data)

            if not is_valid:
                logger.info("OpenUI markup failed initial validation: %s. Attempting 1 repair...", val_errors)
                yield f"event: status\ndata: {json.dumps({'step': 'repair', 'message': 'Verifying numerical grounding and accessibility standards...'})}\n\n"

                # One repair attempt
                repair_prompt = (
                    f"Your previous OpenUI markup failed validation with errors:\n"
                    f"{json.dumps(val_errors)}\n"
                    f"Please rewrite the OpenUI markup ensuring 100% numerical grounding strictly using the tool data."
                )
                contents.append({"role": "user", "parts": [{"text": repair_prompt}]})

                try:
                    repair_resp = await _gemma_client.generate(
                        contents=contents,
                        system_instruction=sys_prompt,
                        user_id=principal.username,
                    )
                    repair_parts = repair_resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    repair_text_parts = [p["text"] for p in repair_parts if "text" in p and not p.get("thought", False)]
                    if not repair_text_parts:
                        repair_text_parts = [p["text"] for p in repair_parts if "text" in p]
                    repair_text = "\n".join(repair_text_parts).strip()
                    rep_valid, rep_errors = validate_openui_output(repair_text, executed_tools_data)
                    if rep_valid:
                        final_markup = repair_text
                        validation_result = "repaired"
                    else:
                        logger.warning("Repair also failed validation: %s. Falling back to ViewSpec.", rep_errors)
                        fallback_used = True
                        validation_result = "fallback"
                except Exception as r_err:
                    logger.warning("Repair generation error: %s. Triggering fallback.", r_err)
                    fallback_used = True
                    validation_result = "fallback"

        except Exception as exc:
            logger.error("Copilot orchestration error: %s. Using deterministic ViewSpec.", exc)
            fallback_used = True
            validation_result = "fallback"
            if not executed_tools_data:
                try:
                    executed_tools_data.append(tool_league_table(principal, LeagueTableArgs()))
                    tools_called_names.append("league_table")
                except Exception as t_err:
                    logger.error("Fallback tool execution error: %s", t_err)

        # 5. Build Fallback ViewSpec if needed
        primary_tool = tools_called_names[0] if tools_called_names else "league_table"
        primary_data = executed_tools_data[0] if executed_tools_data else {}
        try:
            final_view_spec = ViewSpecBuilder.build_from_tool_result(primary_tool, primary_data, fallback=fallback_used)
            if fallback_used or not final_markup:
                final_markup = final_view_spec.to_openui_lang()
        except Exception as v_err:
            logger.error("ViewSpec build failed: %s. Emitting emergency markup.", v_err)
            final_markup = '<Callout type="critical" message="Service communication interrupted. Displaying verified local fallback data." />\n<Card title="Maharashtra State Command Center">\n  <Stat label="Statewide Status" value="Online (Offline Fallback Active)" />\n</Card>'
            final_view_spec = ViewSpecBuilder.build_from_tool_result("league_table", {}, fallback=True)

        # 6. Stream OpenUI Lang Chunk by Chunk
        try:
            chunk_size = 64
            for i in range(0, len(final_markup), chunk_size):
                chunk = final_markup[i:i+chunk_size]
                yield f"event: chunk\ndata: {json.dumps({'text': chunk})}\n\n"
                await asyncio.sleep(0.015)
        except Exception as chunk_err:
            logger.error("Error streaming chunk: %s", chunk_err)

        # 7. Complete and Record Audit (Fail-open)
        total_latency = int((time.time() - start_time) * 1000)
        run_id = uuid.uuid4()
        try:
            recorded_run_id = await record_agent_run(
                principal_id=principal.username,
                principal_role=principal.role,
                model_id=settings.COPILOT_MODEL,
                prompt_version_hash=prompt_hash,
                user_query=user_query,
                language=lang,
                tools_called=executed_tool_calls_audit,
                validation_result=validation_result,
                fallback_used=fallback_used,
                latency_ms=total_latency,
                tool_executions=executed_tool_calls_audit,
            )
            if recorded_run_id:
                run_id = recorded_run_id
        except Exception as audit_err:
            logger.warning("Audit record failed (continuing fail-open): %s", audit_err)

        # 8. Asynchronously Learn User Preference (Fail-open background task)
        try:
            await mem_mgr.add_preference_async(principal.username, principal.role, lang, user_query)
        except Exception as mem_err:
            logger.debug("Memory learning skipped: %s", mem_err)

        # 9. Yield Final Done Event (Guaranteed)
        try:
            done_payload = {
                "run_id": str(run_id),
                "validation_status": validation_result,
                "fallback": fallback_used,
                "as_of": primary_data.get("as_of", datetime.now(timezone.utc).isoformat()) if isinstance(primary_data, dict) else datetime.now(timezone.utc).isoformat(),
                "model_id": settings.COPILOT_MODEL,
                "machine_generated": True,
                "source_status": primary_data.get("source_status", "live") if isinstance(primary_data, dict) else "live",
                "latency_ms": total_latency,
                "view_spec": final_view_spec.model_dump() if hasattr(final_view_spec, "model_dump") else {},
            }
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
        except Exception as done_err:
            logger.error("Error emitting done event: %s", done_err)
            yield f"event: done\ndata: {json.dumps({'run_id': str(run_id), 'fallback': True})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback", summary="Record Officer Thumbs Feedback")
async def copilot_feedback(
    payload: CopilotFeedbackRequest,
    current_user: TokenData = Depends(get_current_user),
):
    """Store thumbs up / thumbs down and optional feedback text."""
    feedback_id = await record_copilot_feedback(
        principal_id=current_user.username,
        rating=payload.rating,
        run_id=payload.run_id,
        reason=payload.reason,
    )
    return {
        "status": "success",
        "feedback_id": str(feedback_id),
        "message": "Feedback recorded successfully.",
    }


@router.get("/memory", summary="Get Officer's Stored Preferences")
async def get_my_memories(
    current_user: TokenData = Depends(get_current_user),
):
    """Retrieve all presentation formatting preferences remembered for the authenticated officer."""
    mem_mgr = get_memory_manager()
    memories = await mem_mgr.get_all_user_memories(current_user.username)
    return {
        "officer": current_user.username,
        "total_preferences": len(memories),
        "preferences": memories,
    }


@router.delete("/memory/{memory_id}", summary="Delete Specific Memory")
async def delete_my_memory(
    memory_id: str,
    current_user: TokenData = Depends(get_current_user),
):
    """Delete a single stored preference."""
    mem_mgr = get_memory_manager()
    success = await mem_mgr.delete_user_memory(current_user.username, memory_id)
    return {"status": "success" if success else "failed", "memory_id": memory_id}


@router.delete("/memory", summary="Purge All Memories (Forget Me)")
async def purge_all_my_memories(
    current_user: TokenData = Depends(get_current_user),
):
    """'Forget Me' action: Purge all presentation memories stored for this officer."""
    mem_mgr = get_memory_manager()
    success = await mem_mgr.delete_all_user_memories(current_user.username)
    return {"status": "success" if success else "failed", "message": "All officer preferences purged."}
