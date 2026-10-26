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
import re
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from eureka.api.auth import TokenData, get_current_user
from eureka.copilot.audit import compute_prompt_version_hash, record_agent_run, record_copilot_feedback
from eureka.copilot.config import get_copilot_settings
from eureka.copilot.c1_client import C1Client
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
    tool_district_profile,
    DistrictProfileArgs,
    tool_active_rumors,
    ActiveRumorsArgs,
    extract_district_from_query,
    get_source_status,
)
from eureka.copilot.viewspec import ViewSpec, ViewSpecBuilder
from eureka.copilot.intent_router import match_fast_path

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


def _resolve_fallback_tool_and_data(user_query: str, principal: CopilotPrincipal) -> Tuple[str, Dict[str, Any]]:
    """Intelligently determine the most relevant tool to invoke for the user query during fallback."""
    district_code = extract_district_from_query(user_query)
    q_lower = user_query.lower()
    is_rumor_query = any(w in q_lower for w in ["rumor", "rumour", "fake", "claim", "crisis", "sla", "ticket", "fact-check", "अफवा"])

    if district_code:
        if is_rumor_query:
            try:
                data = tool_active_rumors(principal, ActiveRumorsArgs(district_code=district_code))
                return "active_rumors", data
            except Exception as e:
                logger.warning("Fallback active_rumors failed: %s", e)
        try:
            data = tool_district_profile(principal, DistrictProfileArgs(district_code=district_code))
            return "district_profile", data
        except Exception as e:
            logger.warning("Fallback district_profile failed: %s", e)
    elif is_rumor_query:
        try:
            data = tool_active_rumors(principal, ActiveRumorsArgs())
            return "active_rumors", data
        except Exception as e:
            logger.warning("Fallback statewide active_rumors failed: %s", e)

    # Default fallback: statewide league table
    data = tool_league_table(principal, LeagueTableArgs())
    return "league_table", data


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
        auth_time_ms = 0.5
        first_byte_ms: Optional[float] = None
        memory_time_ms = 0.0
        intent_routing_time_ms = 0.0
        model_calls_ms = 0.0
        tool_calls_ms = 0.0
        validation_time_ms = 0.0
        c1_time_ms = 0.0

        user_query = payload.query.strip()
        lang = payload.language if payload.language in ("mr", "hi", "en") else detect_language(user_query)

        # 1. Yield Initial Status
        if first_byte_ms is None:
            first_byte_ms = max(0.1, round((time.time() - start_time) * 1000, 2))
        yield f"event: status\ndata: {json.dumps({'step': 'init', 'message': 'Processing query...', 'language': lang})}\n\n"

        # 2. Retrieve Mem0 Preferences (Bounded 800ms fail-open)
        mem_mgr = get_memory_manager()
        t_mem_start = time.time()
        try:
            preferences = await asyncio.wait_for(mem_mgr.search_preferences(principal.username, user_query), timeout=0.300)
        except Exception:
            preferences = []
        memory_time_ms = max(0.1, round((time.time() - t_mem_start) * 1000, 2))
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
        fast_path_used = False
        fallback_used = False
        final_markup = ""
        final_view_spec = None

        t_intent_start = time.time()
        fast_match = match_fast_path(user_query, principal)
        intent_routing_time_ms = max(0.1, round((time.time() - t_intent_start) * 1000, 2))

        if fast_match:
            f_tool, f_args, f_data = fast_match
            fast_path_used = True
            fallback_used = True
            tools_called_names.append(f_tool)
            executed_tools_data.append(f_data)
            executed_tool_calls_audit.append({
                "tool_name": f_tool,
                "tool_args": f_args,
                "tool_status": "success" if "error" not in f_data else "error",
                "duration_ms": 1,
            })
            yield f"event: status\ndata: {json.dumps({'step': 'tool_call', 'tool': f_tool, 'args': f_args, 'provenance': 'fast_path'})}\n\n"

            final_view_spec = ViewSpecBuilder.build_from_tool_result(f_tool, f_data, fallback=True)
            final_markup = final_view_spec.to_openui_lang()
            if first_byte_ms is None:
                first_byte_ms = max(0.1, round((time.time() - start_time) * 1000, 2))
            yield f"event: chunk\ndata: {json.dumps({'text': final_markup, 'provenance': 'fast_path'})}\n\n"

            # 2d Background upgrade with 6s deadline
            if settings.COPILOT_UI_ENGINE == "c1":
                try:
                    t_c1_start = time.time()
                    c1_client = C1Client()
                    c1_res = await asyncio.wait_for(
                        c1_client.generate_ui(f_tool, f_data, user_query, language=lang),
                        timeout=6.0,
                    )
                    c1_time_ms = round((time.time() - t_c1_start) * 1000, 2)
                    if c1_res:
                        final_markup = c1_res
                        fallback_used = False
                        yield f"event: chunk\ndata: {json.dumps({'text': final_markup, 'provenance': 'c1_upgrade', 'replace': True})}\n\n"
                except Exception as c1_err:
                    logger.info("C1 upgrade skipped or timed out: %s", c1_err)
            else:
                try:
                    t_narrative_start = time.time()
                    brief_data = json.dumps(f_data.get("data", {}))[:600]
                    narrative_prompt = f"Provide a brief 2-sentence executive summary in {lang.upper()} for DGIPR officers regarding these governance findings: {brief_data}"
                    upgrade_contents = [{"role": "user", "parts": [{"text": narrative_prompt}]}]
                    upgrade_resp = await asyncio.wait_for(
                        _gemma_client.generate(
                            contents=upgrade_contents,
                            system_instruction=sys_prompt,
                            user_id=principal.username,
                        ),
                        timeout=6.0,
                    )
                    model_calls_ms += (time.time() - t_narrative_start) * 1000
                    candidates = upgrade_resp.get("candidates", [])
                    if candidates:
                        parts = candidates[0].get("content", {}).get("parts", [])
                        narrative_text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                        if narrative_text:
                            upgraded_markup = f"{final_markup}\n\n<Callout type=\"info\" message={json.dumps(narrative_text)} />"
                            clean_upgraded, val_status = validate_openui_output(upgraded_markup, executed_tools_data)
                            if val_status == "valid":
                                final_markup = clean_upgraded
                                yield f"event: chunk\ndata: {json.dumps({'text': final_markup, 'provenance': 'model_upgrade', 'replace': True})}\n\n"
                except Exception as up_err:
                    logger.info("Narrative upgrade skipped or timed out: %s", up_err)

        try:
            # First turn: Ask model for tool calls
            if not fast_path_used:
                yield f"event: status\ndata: {json.dumps({'step': 'analyzing', 'message': 'Consulting DGIPR analytical data services...'})}\n\n"

            turn_count = 0
            max_turns = 0 if fast_path_used else 4

            while turn_count < max_turns:
                turn_count += 1
                t_model_start = time.time()
                response = await _gemma_client.generate(
                    contents=contents,
                    system_instruction=sys_prompt,
                    tools=tool_declarations,
                    user_id=principal.username,
                )
                model_calls_ms += (time.time() - t_model_start) * 1000

                candidates = response.get("candidates", [])
                if not candidates:
                    break

                parts = candidates[0].get("content", {}).get("parts", [])
                if not parts:
                    break

                # Check for function calls (handle ALL functionCall parts concurrently)
                fn_parts = [p for p in parts if "functionCall" in p]
                if fn_parts:
                    for p in fn_parts:
                        fc = p["functionCall"]
                        fn_name = fc.get("name")
                        fn_args = fc.get("args", {})
                        tools_called_names.append(fn_name)
                        yield f"event: status\ndata: {json.dumps({'step': 'tool_call', 'tool': fn_name, 'args': fn_args})}\n\n"

                    async def _run_single_tool(fc_dict: Dict[str, Any]):
                        f_name = fc_dict.get("name")
                        f_args = fc_dict.get("args", {})
                        t0 = time.time()
                        tool_def = COPILOT_TOOLS_MAP.get(f_name)
                        if tool_def:
                            arg_model, fn_impl = tool_def
                            try:
                                parsed_args = arg_model(**f_args)
                                tool_out = fn_impl(principal, parsed_args)
                                tool_status = "success"
                            except Exception as t_err:
                                tool_out = {"error": "EXECUTION_ERROR", "message": str(t_err), "source_status": "unavailable"}
                                tool_status = "error"
                        else:
                            tool_out = {"error": "UNKNOWN_TOOL", "message": f"Tool '{f_name}' does not exist.", "source_status": "unavailable"}
                            tool_status = "error"
                        dur_ms = int((time.time() - t0) * 1000)
                        return f_name, f_args, tool_out, tool_status, dur_ms

                    results = await asyncio.gather(*[_run_single_tool(p["functionCall"]) for p in fn_parts])

                    user_resp_parts = []
                    for f_name, f_args, tool_out, tool_status, dur_ms in results:
                        tool_calls_ms += dur_ms
                        executed_tools_data.append(tool_out)
                        executed_tool_calls_audit.append({
                            "tool_name": f_name,
                            "tool_args": f_args,
                            "tool_status": tool_status,
                            "duration_ms": dur_ms,
                        })
                        user_resp_parts.append({
                            "functionResponse": {
                                "name": f_name,
                                "response": tool_out,
                            }
                        })

                    # Append to conversation
                    contents.append({
                        "role": "model",
                        "parts": parts,
                    })
                    contents.append({
                        "role": "user",
                        "parts": user_resp_parts,
                    })
                    continue

                # If no function call, check for non-thought text output
                text_parts = [p["text"] for p in parts if "text" in p and not p.get("thought", False)]
                if not text_parts:
                    text_parts = [p["text"] for p in parts if "text" in p]

                if text_parts:
                    raw_text = "\n".join(text_parts).strip()
                    component_match = re.search(r'<(?:Stack|Heading|KpiCard|Callout|DataTable|BarChart|LineChart|PieChart|GraphView|Card|Text)\b', raw_text)
                    if component_match and component_match.start() > 0:
                        final_markup = raw_text[component_match.start():].strip()
                    else:
                        final_markup = raw_text
                    break

            # If no tools were called, resolve fallback tool scoped to caller query
            if not executed_tools_data:
                fallback_tool_name, default_res = _resolve_fallback_tool_and_data(user_query, principal)
                executed_tools_data.append(default_res)
                executed_tool_calls_audit.append({
                    "tool_name": fallback_tool_name,
                    "tool_args": {"query_resolved": True},
                    "tool_status": "success",
                    "duration_ms": 10,
                })
                tools_called_names.append(fallback_tool_name)

            # 3.5 Thesys C1 Engine Option
            if settings.COPILOT_UI_ENGINE == "c1":
                yield f"event: status\ndata: {json.dumps({'step': 'c1', 'message': 'Generating presentation via Thesys C1 engine...'})}\n\n"
                t_c1_start = time.time()
                primary_t = tools_called_names[0] if tools_called_names else "league_table"
                primary_d = executed_tools_data[0] if executed_tools_data else {}
                try:
                    c1_client = C1Client()
                    c1_out = await c1_client.generate_ui(primary_t, primary_d, user_query, language=lang)
                    c1_time_ms = round((time.time() - t_c1_start) * 1000, 2)
                    final_markup = c1_out
                except Exception as c1_err:
                    c1_time_ms = round((time.time() - t_c1_start) * 1000, 2)
                    logger.warning("Thesys C1 failed: %s. Falling back to deterministic ViewSpec.", c1_err)
                    fallback_used = True
                    validation_result = "fallback"

            # 4. Validate Generated OpenUI Lang
            if not fallback_used:
                t_val_start = time.time()
                is_valid, val_errors = validate_openui_output(final_markup, executed_tools_data)
                validation_time_ms += (time.time() - t_val_start) * 1000
            else:
                is_valid = False
                val_errors = ["C1 fallback active"]

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
                    t_rep_model = time.time()
                    repair_resp = await _gemma_client.generate(
                        contents=contents,
                        system_instruction=sys_prompt,
                        user_id=principal.username,
                    )
                    model_calls_ms += (time.time() - t_rep_model) * 1000
                    repair_parts = repair_resp.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    repair_text_parts = [p["text"] for p in repair_parts if "text" in p and not p.get("thought", False)]
                    if not repair_text_parts:
                        repair_text_parts = [p["text"] for p in repair_parts if "text" in p]
                    raw_rep = "\n".join(repair_text_parts).strip()
                    comp_rep = re.search(r'<(?:Stack|Heading|KpiCard|Callout|DataTable|BarChart|LineChart|PieChart|GraphView|Card|Text)\b', raw_rep)
                    if comp_rep and comp_rep.start() > 0:
                        repair_text = raw_rep[comp_rep.start():].strip()
                    else:
                        repair_text = raw_rep
                    t_rep_val = time.time()
                    rep_valid, rep_errors = validate_openui_output(repair_text, executed_tools_data)
                    validation_time_ms += (time.time() - t_rep_val) * 1000
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
                    fallback_tool_name, default_res = _resolve_fallback_tool_and_data(user_query, principal)
                    executed_tools_data.append(default_res)
                    tools_called_names.append(fallback_tool_name)
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
            chunk_size = 65536
            for i in range(0, len(final_markup), chunk_size):
                chunk = final_markup[i:i+chunk_size]
                if not fast_path_used:
                    yield f"event: chunk\ndata: {json.dumps({'text': chunk})}\n\n"
                pass
        except Exception as chunk_err:
            logger.error("Error streaming chunk: %s", chunk_err)

        # 7. Complete and Record Audit (Fail-open)
        last_byte_ms = round((time.time() - start_time) * 1000, 2)
        total_latency = int(last_byte_ms)
        stage_timings = {
            "auth_ms": round(auth_time_ms, 2),
            "memory_ms": round(memory_time_ms, 2),
            "intent_routing_ms": round(intent_routing_time_ms, 2),
            "model_calls_ms": round(model_calls_ms, 2),
            "tool_calls_ms": round(tool_calls_ms, 2),
            "validation_ms": round(validation_time_ms, 2),
            "c1_ms": round(c1_time_ms, 2),
            "first_byte_ms": round(first_byte_ms or 0.1, 2),
            "last_byte_ms": round(last_byte_ms, 2),
            "total_latency_ms": round(last_byte_ms, 2),
        }
        server_timing_str = (
            f"auth;dur={stage_timings['auth_ms']}, "
            f"memory;dur={stage_timings['memory_ms']}, "
            f"intent;dur={stage_timings['intent_routing_ms']}, "
            f"model;dur={stage_timings['model_calls_ms']}, "
            f"tools;dur={stage_timings['tool_calls_ms']}, "
            f"val;dur={stage_timings['validation_ms']}, "
            f"c1;dur={stage_timings['c1_ms']}, "
            f"first_byte;dur={stage_timings['first_byte_ms']}, "
            f"total;dur={stage_timings['total_latency_ms']}"
        )

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
                stage_timings=stage_timings,
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
                "engine": "c1" if (settings.COPILOT_UI_ENGINE == "c1" and not fallback_used) else ("deterministic" if fallback_used else "markup"),
                "model_id": settings.C1_MODEL_ID if (settings.COPILOT_UI_ENGINE == "c1" and not fallback_used) else settings.COPILOT_MODEL,
                "machine_generated": True,
                "source_status": primary_data.get("source_status", "live") if isinstance(primary_data, dict) else "live",
                "latency_ms": total_latency,
                "view_spec": final_view_spec.model_dump() if (fallback_used and hasattr(final_view_spec, "model_dump")) else None,
                "timings": stage_timings,
                "server_timing": server_timing_str,
            }
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"
        except Exception as done_err:
            logger.error("Error emitting done event: %s", done_err)
            yield f"event: done\ndata: {json.dumps({'run_id': str(run_id), 'fallback': True, 'timings': stage_timings, 'server_timing': server_timing_str})}\n\n"

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
