"""Propose-only LLM Planner with mandatory entity grounding check.

Invoked ONLY when parser confidence is below threshold (< 0.7) and planner mode is enabled.
Collects proposed function calls from Gemma WITHOUT executing them.
Enforces strict grounding: drops any proposed operation referencing a district
that was not resolved by the gazetteer in the original user query.
"""

import asyncio
import logging
from typing import List, Optional

from eureka.copilot.policy.principal import PolicyPrincipal
from eureka.copilot.policy.matrix import Intent
from eureka.copilot.planning.gazetteer import resolve_entities, get_district_name
from eureka.copilot.planning.plan import Op, ParsedQuery
from eureka.copilot.tools import COPILOT_TOOLS_MAP, get_copilot_function_declarations, normalize_district_code
from eureka.copilot.gemma_client import get_gemma_client

logger = logging.getLogger("eureka.copilot.planning.llm_planner")

_TOOL_TO_INTENT: dict[str, Intent] = {
    "league_table": Intent.LEAGUE,
    "district_profile": Intent.PROFILE,
    "pillar_breakdown": Intent.PILLAR,
    "trend": Intent.TREND,
    "compare_districts": Intent.COMPARE,
    "active_rumors": Intent.RUMORS,
    "forecast": Intent.FORECAST,
    "neighbors": Intent.NEIGHBORS,
    "division_rollup": Intent.DIVISION_ROLLUP,
    "dossier_summary": Intent.DOSSIER,
}


async def plan_with_llm(
    query: str,
    parser_fallback: ParsedQuery,
    principal: Optional[PolicyPrincipal] = None,
    timeout_seconds: float = 3.0,
) -> ParsedQuery:
    """Propose candidate operations using Gemma, strictly grounded against query entities."""
    gemma = get_gemma_client()
    if not gemma.is_available():
        return parser_fallback

    # 1. Resolve permitted grounded districts from the raw query
    query_entities = resolve_entities(query, principal=principal)
    grounded_districts = {e.code.upper() for e in query_entities}
    if principal and principal.district_code:
        grounded_districts.add(principal.district_code.upper())

    # 2. Build isolated prompt without memory, tool data, or principal details
    system_instruction = (
        "You are an intent planning parser for Maharashtra State Media Governance.\n"
        "Analyze the user query and output function calls for the required information tools.\n"
        "Do NOT answer in text; only propose function calls.\n"
        "Never propose districts that are not explicitly requested by the user."
    )
    user_content = f"<user_query>{query.strip()}</user_query>"

    tool_declarations = [{"functionDeclarations": get_copilot_function_declarations()}]

    try:
        response = await asyncio.wait_for(
            gemma.generate(
                system_instruction=system_instruction,
                contents=[{"role": "user", "parts": [{"text": user_content}]}],
                tools=tool_declarations,
            ),
            timeout=timeout_seconds,
        )

        candidates = response.get("candidates", [])
        if not candidates:
            return parser_fallback

        parts = candidates[0].get("content", {}).get("parts", [])
        proposed_ops: List[Op] = []
        op_counter = 1

        for part in parts:
            fn_call = part.get("functionCall")
            if not fn_call:
                continue

            tool_name = fn_call.get("name")
            args = fn_call.get("args", {})

            if tool_name not in COPILOT_TOOLS_MAP:
                continue

            # Validate tool arguments with tool's own Pydantic model
            arg_model_cls, _ = COPILOT_TOOLS_MAP[tool_name]
            try:
                validated_args = arg_model_cls(**args).model_dump()
            except Exception:
                continue

            # Extract referenced districts
            referenced_districts: List[str] = []
            if "district_code" in validated_args and validated_args["district_code"]:
                raw_c = str(validated_args["district_code"])
                norm_c = normalize_district_code(raw_c) or raw_c.upper()
                validated_args["district_code"] = norm_c
                referenced_districts.append(norm_c)
            if "district_codes" in validated_args and isinstance(validated_args["district_codes"], list):
                norm_list = []
                for d in validated_args["district_codes"]:
                    raw_c = str(d)
                    norm_c = normalize_district_code(raw_c) or raw_c.upper()
                    norm_list.append(norm_c)
                    referenced_districts.append(norm_c)
                validated_args["district_codes"] = norm_list

            # MANDATORY GROUNDING CHECK (§6.7)
            # Every district proposed MUST exist in grounded_districts from the user query
            if referenced_districts:
                if any(d not in grounded_districts for d in referenced_districts):
                    logger.warning(
                        "llm_planner.ungrounded_entity_dropped: tool %s proposed ungrounded %s",
                        tool_name,
                        referenced_districts,
                    )
                    continue

            intent = _TOOL_TO_INTENT.get(tool_name, Intent.PROFILE)
            op_id = f"o{op_counter}"
            op_counter += 1

            first_dist = referenced_districts[0] if referenced_districts else "MH"
            proposed_ops.append(Op(
                op_id=op_id,
                intent=intent,
                tool=tool_name,
                args=validated_args,
                districts=tuple(referenced_districts),
                group=f"{first_dist}:{intent.value}",
                label=f"{get_district_name(first_dist)} · {intent.value.title()}",
                defaulted_scope=False,
                source="llm",
            ))

        if proposed_ops:
            return ParsedQuery(
                ops=tuple(proposed_ops),
                confidence=0.85,
                residual_tokens=(),
                clarifications=(),
            )

    except Exception as exc:
        logger.warning("llm_planner.fallback_to_parser: %s", exc)

    return parser_fallback
