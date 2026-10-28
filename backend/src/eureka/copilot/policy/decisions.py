"""Decision model, verdicts, reasons, and sealed AuthorizedOp capability.

AuthorizedOp represents an operation that has passed in-process policy verification.
It cannot be instantiated directly outside the policy engine.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

POLICY_VERSION = "2026.10.1"


class Verdict(str, Enum):
    """Authoritative authorization verdict."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    INDETERMINATE = "INDETERMINATE"  # Treated strictly as DENY


class Reason(str, Enum):
    """Detailed deterministic reason codes for audit and telemetry."""
    OK = "OK"
    ROLE_NOT_PERMITTED = "ROLE_NOT_PERMITTED"
    DISTRICT_OUT_OF_SCOPE = "DISTRICT_OUT_OF_SCOPE"
    DEPENDENCY_DENIED = "DEPENDENCY_DENIED"
    UNKNOWN_ENTITY = "UNKNOWN_ENTITY"
    UNGROUNDED_ENTITY = "UNGROUNDED_ENTITY"
    SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    POLICY_ERROR = "POLICY_ERROR"


@dataclass(frozen=True)
class Scope:
    """Explicit resolved district scope boundary."""
    districts: frozenset[str]


@dataclass(frozen=True)
class Decision:
    """Evaluation result for a single candidate operation."""
    op_id: str
    verdict: Verdict
    reason: Reason
    scope: Optional[Scope]
    policy_version: str
    decision_id: str


# Module-private seal token imported only by engine.py
_SEAL = object()


@dataclass(frozen=True)
class AuthorizedOp:
    """Sealed capability representing a policy-authorized operation.

    The executor accepts ONLY instances of AuthorizedOp.
    """
    op: Any
    scope: Scope
    decision_id: str
    policy_version: str
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        if self._seal is not _SEAL:
            raise PermissionError("AuthorizedOp can only be created by the policy engine.")
