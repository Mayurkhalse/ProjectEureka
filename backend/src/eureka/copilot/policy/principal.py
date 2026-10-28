"""Policy principal definitions and trust boundary validation.

Identity (role, district, division) is constructed only from a verified token.
Inconsistent, unknown, or unassigned identities fail closed with PrincipalError.
"""

from dataclasses import dataclass
from typing import Any, Optional

from eureka.core.reference_data import DISTRICTS, DIVISIONS
from eureka.copilot.policy.roles import Role, to_role


class PrincipalError(Exception):
    """Raised when token identity fails strict structural validation."""
    pass


# Single source of truth derived directly from authoritative reference data
ALL_DISTRICT_CODES: frozenset[str] = frozenset(d[0] for d in DISTRICTS)

# Mapping: district_code -> (division_code, division_name_en)
DISTRICT_TO_DIVISION_INFO: dict[str, tuple[str, str]] = {
    d[0]: (d[1], next(div[1] for div in DIVISIONS if div[0] == d[1]))
    for d in DISTRICTS
}

# Canonical set of valid division identifiers (both code and English name)
CANONICAL_DIVISIONS: dict[str, str] = {}
for div in DIVISIONS:
    code = div[0]
    name_en = div[1]
    CANONICAL_DIVISIONS[code.upper()] = code
    CANONICAL_DIVISIONS[name_en.upper()] = code


@dataclass(frozen=True)
class PolicyPrincipal:
    """Immutable, policy-verified principal identity."""
    username: str
    role: Role
    district_code: Optional[str]
    division: Optional[str]


def build_principal(
    token_or_user: Any,
    *,
    division_claim: Optional[str] = None,
) -> PolicyPrincipal:
    """Construct and strictly validate a PolicyPrincipal from verified token data.

    Raises PrincipalError if:
      - Role cannot be mapped to an authoritative Role via exact match.
      - DISTRICT_COLLECTOR or DIO_DESK has missing/invalid district_code.
      - DIVISION_HEAD has missing or unrecognized division.
    """
    if not token_or_user:
        raise PrincipalError("Empty token or principal data provided.")

    # Extract username
    username = getattr(token_or_user, "username", None)
    if not username and isinstance(token_or_user, dict):
        username = token_or_user.get("username") or token_or_user.get("sub")
    if not username:
        raise PrincipalError("Principal identity is missing username.")

    # Extract raw role
    raw_role = getattr(token_or_user, "role", None)
    if raw_role is None and isinstance(token_or_user, dict):
        raw_role = token_or_user.get("role")
    if hasattr(raw_role, "value"):
        raw_role = raw_role.value

    role = to_role(str(raw_role) if raw_role is not None else None)
    if role is None:
        raise PrincipalError(f"Principal '{username}' has unassigned or unrecognized role: {raw_role}")

    # Extract district_code
    district_code = getattr(token_or_user, "district_code", None)
    if district_code is None and isinstance(token_or_user, dict):
        district_code = token_or_user.get("district_code")
    if district_code:
        district_code = str(district_code).strip().upper()

    # Extract explicit division claim if any
    div_claim = division_claim or getattr(token_or_user, "division", None)
    if div_claim is None and isinstance(token_or_user, dict):
        div_claim = token_or_user.get("division")
    if div_claim:
        div_claim = str(div_claim).strip()

    # Role-specific invariant validation
    if role in (Role.DISTRICT_COLLECTOR, Role.DIO_DESK):
        if not district_code or district_code not in ALL_DISTRICT_CODES:
            raise PrincipalError(
                f"Role '{role.value}' for user '{username}' requires valid district assignment. Got: '{district_code}'"
            )
        # Invariant: Division is ALWAYS strictly derived from the assigned district
        div_info = DISTRICT_TO_DIVISION_INFO[district_code]
        effective_division = div_info[1]  # English division name, e.g. "Nashik"

    elif role == Role.DIVISION_HEAD:
        if not div_claim:
            raise PrincipalError(
                f"Role 'DIVISION_HEAD' for user '{username}' requires a verified division claim."
            )
        matched_code = CANONICAL_DIVISIONS.get(div_claim.upper())
        if not matched_code:
            raise PrincipalError(
                f"Role 'DIVISION_HEAD' for user '{username}' has invalid division: '{div_claim}'"
            )
        # Use English division name as canonical label (e.g. "Nashik")
        effective_division = next(div[1] for div in DIVISIONS if div[0] == matched_code)
        # Division head does not require a single district_code
        district_code = None

    elif role == Role.STATE_ADMIN:
        effective_division = None
        # State admin has statewide scope; district_code is optional
        if district_code and district_code not in ALL_DISTRICT_CODES:
            district_code = None
    else:
        raise PrincipalError(f"Unhandled role validation: {role}")

    return PolicyPrincipal(
        username=username,
        role=role,
        district_code=district_code,
        division=effective_division,
    )


def to_legacy(p: PolicyPrincipal) -> Any:
    """Convert PolicyPrincipal to legacy CopilotPrincipal for existing tools."""
    from eureka.copilot.tools import CopilotPrincipal
    return CopilotPrincipal(
        username=p.username,
        role=p.role.value,
        district_code=p.district_code,
        division=p.division,
    )
