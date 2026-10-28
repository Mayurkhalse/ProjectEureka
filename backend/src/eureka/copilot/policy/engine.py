"""Authoritative in-process Policy Engine.

Evaluates candidate operations independently against the permission matrix.
Decisions fail closed on any ambiguity or exception.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, List, Dict, Optional

from eureka.copilot.policy.roles import Role
from eureka.copilot.policy.principal import PolicyPrincipal
from eureka.copilot.policy.matrix import (
    Intent,
    ScopeKind,
    RULES,
    allowed_districts,
    default_districts,
)
from eureka.copilot.policy.decisions import (
    Verdict,
    Reason,
    Scope,
    Decision,
    AuthorizedOp,
    POLICY_VERSION,
    _SEAL,
)

logger = logging.getLogger("eureka.copilot.policy.engine")


@dataclass
class PlanContext:
    """Evaluation context tracking dependency verdicts within a plan."""
    decisions: Dict[str, Decision] = field(default_factory=dict)

    def verdict(self, op_id: str) -> Optional[Verdict]:
        d = self.decisions.get(op_id)
        return d.verdict if d else None


@dataclass
class PlanDecision:
    """Aggregated plan authorization result."""
    allowed: List[AuthorizedOp]
    denied: List[Decision]
    decisions: Dict[str, Decision]


def source_available(tool: str, settings: Any) -> bool:
    """Check if the data source behind a tool is available under current environment.

    Per §7.4: In production, synthetic and heuristic tools (trend, forecast) are
    blocked with SOURCE_NOT_AVAILABLE unless COPILOT_DEMO_MODE is True.
    """
    demo_mode = getattr(settings, "COPILOT_DEMO_MODE", False)
    if not demo_mode:
        if tool in ("trend", "forecast"):
            return False
    return True


def _make_decision(
    op_id: str,
    verdict: Verdict,
    reason: Reason,
    scope: Optional[Scope] = None,
) -> Decision:
    return Decision(
        op_id=op_id,
        verdict=verdict,
        reason=reason,
        scope=scope,
        policy_version=POLICY_VERSION,
        decision_id=str(uuid.uuid4()),
    )


def decide(
    p: PolicyPrincipal,
    op: Any,
    ctx: PlanContext,
    settings: Any = None,
) -> Decision:
    """Authorize a single candidate operation.

    Guarantees:
      - Always returns a Decision; never raises.
      - Any unhandled exception fails closed to INDETERMINATE with Reason.POLICY_ERROR.
    """
    op_id = getattr(op, "op_id", "op_unknown")
    try:
        intent = getattr(op, "intent", None)
        if isinstance(intent, str):
            try:
                intent = Intent(intent)
            except ValueError:
                return _make_decision(op_id, Verdict.DENY, Reason.ROLE_NOT_PERMITTED)

        role_rules = RULES.get(p.role, {})
        kind = role_rules.get(intent, ScopeKind.NONE)

        if kind == ScopeKind.NONE:
            return _make_decision(op_id, Verdict.DENY, Reason.ROLE_NOT_PERMITTED)

        allowed = allowed_districts(p, kind)
        op_districts = getattr(op, "districts", ())
        requested = frozenset(op_districts) or default_districts(p, intent, kind)

        # Non-empty scope required for all district-dependent operations
        if not requested or not (requested <= allowed):
            return _make_decision(op_id, Verdict.DENY, Reason.DISTRICT_OUT_OF_SCOPE)

        # Compare requires at least 2 distinct authorized districts
        if intent == Intent.COMPARE and len(requested) < 2:
            return _make_decision(op_id, Verdict.DENY, Reason.DISTRICT_OUT_OF_SCOPE)

        # Check dependencies
        depends_on = getattr(op, "depends_on", ())
        if depends_on:
            if any(ctx.verdict(dep) != Verdict.ALLOW for dep in depends_on):
                return _make_decision(op_id, Verdict.DENY, Reason.DEPENDENCY_DENIED)

        # Check source availability (gating synthetic/heuristic tools in production)
        tool_name = getattr(op, "tool", "")
        if not source_available(tool_name, settings):
            return _make_decision(op_id, Verdict.DENY, Reason.SOURCE_NOT_AVAILABLE)

        return _make_decision(op_id, Verdict.ALLOW, Reason.OK, Scope(requested))

    except Exception as exc:
        logger.exception("policy.error for op %s: %s", op_id, exc)
        return _make_decision(op_id, Verdict.INDETERMINATE, Reason.POLICY_ERROR)


def authorize_plan(
    p: PolicyPrincipal,
    plan: Any,
    settings: Any = None,
) -> PlanDecision:
    """Authorize an entire candidate plan with dependency ordering and limit enforcement."""
    max_ops = getattr(settings, "COPILOT_MAX_OPS", 6)
    ctx = PlanContext()
    allowed_ops: List[AuthorizedOp] = []
    denied_ops: List[Decision] = []

    ops = getattr(plan, "ops", ())
    for idx, op in enumerate(ops):
        op_id = getattr(op, "op_id", f"o{idx+1}")

        # Enforce max operations cap
        if idx >= max_ops:
            d = _make_decision(op_id, Verdict.DENY, Reason.LIMIT_EXCEEDED)
            ctx.decisions[op_id] = d
            denied_ops.append(d)
            continue

        d = decide(p, op, ctx, settings)
        ctx.decisions[op_id] = d

        if d.verdict == Verdict.ALLOW and d.scope is not None:
            authorized = AuthorizedOp(
                op=op,
                scope=d.scope,
                decision_id=d.decision_id,
                policy_version=POLICY_VERSION,
                _seal=_SEAL,
            )
            allowed_ops.append(authorized)
        else:
            denied_ops.append(d)

    return PlanDecision(
        allowed=allowed_ops,
        denied=denied_ops,
        decisions=ctx.decisions,
    )
