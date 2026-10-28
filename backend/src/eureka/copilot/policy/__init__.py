"""Policy engine package for Nirdeshak Copilot.

Single source of truth for authorization, principal verification,
and result scoping.
"""

from eureka.copilot.policy.roles import Role, to_role
from eureka.copilot.policy.principal import PolicyPrincipal, PrincipalError, build_principal, to_legacy
from eureka.copilot.policy.matrix import Intent, ScopeKind, RULES, allowed_districts, default_districts
from eureka.copilot.policy.decisions import (
    Verdict,
    Reason,
    Scope,
    Decision,
    AuthorizedOp,
    POLICY_VERSION,
)
from eureka.copilot.policy.engine import decide, authorize_plan, PlanDecision, PlanContext
from eureka.copilot.policy.scope_filter import filter_result, ScopeFilterError
from eureka.copilot.policy.memory_gate import MemoryGate

__all__ = [
    "Role",
    "to_role",
    "PolicyPrincipal",
    "PrincipalError",
    "build_principal",
    "to_legacy",
    "Intent",
    "ScopeKind",
    "RULES",
    "allowed_districts",
    "default_districts",
    "Verdict",
    "Reason",
    "Scope",
    "Decision",
    "AuthorizedOp",
    "POLICY_VERSION",
    "decide",
    "authorize_plan",
    "PlanDecision",
    "PlanContext",
    "filter_result",
    "ScopeFilterError",
    "MemoryGate",
]
