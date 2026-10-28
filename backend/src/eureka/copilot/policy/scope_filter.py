"""Output Scope Enforcement Filter.

Post-execution enforcement: inspects tool responses and removes any record
whose district_code is outside the authorized scope. Fails closed with ScopeFilterError.
"""

import copy
import logging
from typing import Any, Dict

from eureka.copilot.policy.decisions import Scope

logger = logging.getLogger("eureka.copilot.policy.scope_filter")


class ScopeFilterError(Exception):
    """Raised when output cannot be safely scoped or contains unauthorized structures."""
    pass


def filter_result(tool: str, result: Dict[str, Any], scope: Scope) -> Dict[str, Any]:
    """Filter tool output to ensure zero data leakage beyond scope.districts.

    Raises ScopeFilterError if the structure is unexpected and cannot be verified.
    """
    if not isinstance(result, dict):
        raise ScopeFilterError(f"Expected dict from tool '{tool}', got {type(result).__name__}")

    # Pass through tool-level errors as-is
    if "error" in result:
        return result

    scoped = copy.deepcopy(result)
    allowed = scope.districts

    # Resolve data container if nested under "data"
    target = scoped.get("data") if isinstance(scoped.get("data"), dict) else scoped

    if tool == "league_table":
        if "districts" in target and isinstance(target["districts"], list):
            original_len = len(target["districts"])
            target["districts"] = [
                d for d in target["districts"]
                if isinstance(d, dict) and d.get("district_code", "").upper() in allowed
            ]
            if len(target["districts"]) < original_len:
                logger.info("scope_filter.removed: pruned %d districts from league_table", original_len - len(target["districts"]))
            target["total_count"] = len(target["districts"])
            return scoped
        raise ScopeFilterError("league_table missing valid districts list")

    elif tool == "compare_districts":
        if "districts" in target and isinstance(target["districts"], list):
            original_len = len(target["districts"])
            target["districts"] = [
                d for d in target["districts"]
                if isinstance(d, dict) and d.get("district_code", "").upper() in allowed
            ]
            if len(target["districts"]) < original_len:
                logger.info("scope_filter.removed: pruned %d districts from compare_districts", original_len - len(target["districts"]))
            target["count"] = len(target["districts"])
            return scoped
        raise ScopeFilterError("compare_districts missing valid districts list")

    elif tool == "active_rumors":
        if "tickets" in target and isinstance(target["tickets"], list):
            original_len = len(target["tickets"])
            target["tickets"] = [
                t for t in target["tickets"]
                if isinstance(t, dict) and (t.get("district_code") or t.get("districtCode", "")).upper() in allowed
            ]
            if len(target["tickets"]) < original_len:
                logger.info("scope_filter.removed: pruned %d tickets from active_rumors", original_len - len(target["tickets"]))
            target["total_tickets"] = len(target["tickets"])
            return scoped
        raise ScopeFilterError("active_rumors missing valid tickets list")

    elif tool == "division_rollup":
        if "districts" in target and isinstance(target["districts"], list):
            target["districts"] = [
                d for d in target["districts"]
                if isinstance(d, dict) and d.get("district_code", "").upper() in allowed
            ]
            return scoped
        raise ScopeFilterError("division_rollup missing valid districts list")

    elif tool == "neighbors":
        if "nodes" in target and isinstance(target["nodes"], list):
            # Keep nodes that are within allowed scope
            target["nodes"] = [
                n for n in target["nodes"]
                if isinstance(n, dict) and n.get("id", "").upper() in allowed
            ]
            valid_node_ids = {n["id"].upper() for n in target["nodes"]}
            if "edges" in target and isinstance(target["edges"], list):
                target["edges"] = [
                    e for e in target["edges"]
                    if isinstance(e, dict)
                    and e.get("source", "").upper() in valid_node_ids
                    and e.get("target", "").upper() in valid_node_ids
                ]
            return scoped
        raise ScopeFilterError("neighbors missing valid nodes list")

    elif tool in ("district_profile", "pillar_breakdown", "trend", "forecast", "dossier_summary"):
        # Single-district verification
        d_code = target.get("district_code") or target.get("districtCode")
        if d_code:
            if d_code.upper() not in allowed:
                raise ScopeFilterError(
                    f"Tool '{tool}' returned district '{d_code}' which is outside authorized scope: {allowed}"
                )
        return scoped

    # If any other tool is added without explicit filter handling, check for district_code
    d_code = target.get("district_code")
    if d_code and d_code.upper() not in allowed:
        raise ScopeFilterError(f"Unauthorized district '{d_code}' found in result of tool '{tool}'")

    return scoped
