"""Sole Tool Execution Gate and Concurrency Orchestrator.

The executor is the ONLY module permitted to import and invoke tool callables.
Accepts strictly AuthorizedOp instances; unsealed or arbitrary callers are rejected.
Applies bounded concurrency, per-operation timeouts, output scoping, and failure isolation.
"""

import asyncio
import logging
import time
from typing import Any, List, Optional
from unittest.mock import patch

from eureka.copilot.policy.principal import PolicyPrincipal, to_legacy
from eureka.copilot.policy.decisions import AuthorizedOp
from eureka.copilot.policy.scope_filter import filter_result
from eureka.copilot.execution.results import OpResult, DataQuality
from eureka.copilot.tools import COPILOT_TOOLS_MAP

logger = logging.getLogger("eureka.copilot.execution.executor")


def _resolve_data_quality(tool: str, raw_data: Any) -> DataQuality:
    """Assign data quality tag according to authoritative defect audit (§7.3)."""
    if tool == "trend":
        return "synthetic"
    if tool == "forecast":
        return "heuristic"
    if tool == "active_rumors":
        return "pipeline_memory"
    if tool == "neighbors":
        return "partial"
    if isinstance(raw_data, dict) and raw_data.get("source_status") in ("demo", "csv", "unavailable"):
        return "seed"
    return "live"


async def execute(
    authorized: List[AuthorizedOp],
    principal: PolicyPrincipal,
    settings: Any = None,
) -> List[OpResult]:
    """Execute authorized operations concurrently with fault isolation."""
    if not authorized:
        return []

    timeout_seconds = getattr(settings, "COPILOT_TOOL_TIMEOUT_SECONDS", 8.0)
    sem = asyncio.Semaphore(4)
    legacy_principal = to_legacy(principal)

    # Per-request memo for tool_query_all_36_districts (§7.1)
    # Avoids repeated expensive media_events aggregations across concurrent ops in the same query
    memo_cache: dict[tuple, Any] = {}

    from eureka.hermes import agent_tools
    original_query_36 = agent_tools.tool_query_all_36_districts

    def memoized_query_36(*args, **kwargs):
        cache_key = (args, tuple(sorted(kwargs.items())))
        if cache_key not in memo_cache:
            memo_cache[cache_key] = original_query_36(*args, **kwargs)
        return memo_cache[cache_key]

    async def run(a: AuthorizedOp) -> OpResult:
        if not isinstance(a, AuthorizedOp):
            raise PermissionError("Executor requires verified AuthorizedOp instance.")

        async with sem:
            t0 = time.monotonic()
            tool_name = a.op.tool
            if tool_name not in COPILOT_TOOLS_MAP:
                return OpResult.failed(a, "error", t0)

            arg_model_cls, fn = COPILOT_TOOLS_MAP[tool_name]
            try:
                # 1. Re-validate arguments with tool's own Pydantic model
                args_obj = arg_model_cls(**a.op.args)

                # 2. Execute tool callable in worker thread with timeout
                raw = await asyncio.wait_for(
                    asyncio.to_thread(fn, legacy_principal, args_obj),
                    timeout=timeout_seconds,
                )

                # 3. Detect internal policy drift
                if isinstance(raw, dict) and raw.get("error") == "PERMISSION_DENIED":
                    logger.error(
                        "policy.drift: Tool returned PERMISSION_DENIED for pre-authorized op %s (%s)",
                        a.op.op_id,
                        tool_name,
                    )
                    return OpResult.failed(a, "policy_drift", t0)

                # 4. Mandatory output scope filter (§5.6)
                scoped = filter_result(tool_name, raw, a.scope)

                # 5. Determine honest data quality tag (§7.3)
                quality = _resolve_data_quality(tool_name, scoped)

                return OpResult.ok(a, scoped, t0, data_quality=quality)

            except asyncio.TimeoutError:
                logger.warning("executor.timeout: Tool '%s' (op %s) exceeded %ss timeout", tool_name, a.op.op_id, timeout_seconds)
                return OpResult.failed(a, "timeout", t0)
            except Exception as exc:
                logger.warning("executor.error: Tool '%s' (op %s) failed: %s", tool_name, a.op.op_id, exc)
                return OpResult.failed(a, "error", t0)

    # Patch memoization for the lifecycle of this query execution only
    with patch.object(agent_tools, "tool_query_all_36_districts", side_effect=memoized_query_36):
        results = await asyncio.gather(*(run(a) for a in authorized))

    return list(results)
