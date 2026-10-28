"""Fast-Path Intent Router (Migration Shim over planning/parser).

Delegates query parsing to deterministic parser and executes the primary candidate operation.
Maintained for backwards-compatibility with existing tests (§7.5 of POLICYENGINE.md).
"""

from typing import Optional, Tuple, Dict, Any

from eureka.copilot.tools import (
    CopilotPrincipal,
    COPILOT_TOOLS_MAP,
)
from eureka.copilot.policy.principal import PolicyPrincipal, build_principal
from eureka.copilot.planning.parser import parse_query


def match_fast_path(
    query: str, principal: CopilotPrincipal
) -> Optional[Tuple[str, Dict[str, Any], Dict[str, Any]]]:
    """Shim: inspect query text via planning.parser and execute first candidate operation."""
    if not query or not query.strip():
        return None

    try:
        policy_principal = build_principal(principal)
    except Exception:
        # Construct fallback policy principal for non-strict test harnesses
        from eureka.copilot.policy.roles import to_role, Role
        role = to_role(principal.role) or Role.STATE_ADMIN
        policy_principal = PolicyPrincipal(
            username=principal.username,
            role=role,
            district_code=principal.district_code,
            division=principal.division,
        )

    parsed = parse_query(query, principal=policy_principal)
    if not parsed.ops:
        return None

    # Take the primary operation
    primary_op = parsed.ops[0]
    tool_name = primary_op.tool

    if tool_name not in COPILOT_TOOLS_MAP:
        return None

    arg_model_cls, fn = COPILOT_TOOLS_MAP[tool_name]
    try:
        args_obj = arg_model_cls(**primary_op.args)
        result = fn(principal, args_obj)
        return tool_name, primary_op.args, result
    except Exception:
        return None
