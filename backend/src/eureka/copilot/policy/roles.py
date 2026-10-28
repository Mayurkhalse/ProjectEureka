"""Roles specification for Nirdeshak Copilot Policy Engine.

Defines the four authoritative roles and exact-match mapping from user role strings.
Substrings and wildcard grants are strictly prohibited.
"""

from enum import Enum
from typing import Optional


class Role(str, Enum):
    """The four authoritative RBAC roles for Nirdeshak Copilot."""
    STATE_ADMIN = "STATE_ADMIN"
    DIVISION_HEAD = "DIVISION_HEAD"
    DISTRICT_COLLECTOR = "DISTRICT_COLLECTOR"
    DIO_DESK = "DIO_DESK"


_EXACT_ROLE_MAP: dict[str, Role] = {
    # Canonical display values
    "DG State Admin": Role.STATE_ADMIN,
    "Division Head": Role.DIVISION_HEAD,
    "District Collector": Role.DISTRICT_COLLECTOR,
    "DIO Desk": Role.DIO_DESK,

    # Canonical internal names
    "STATE_ADMIN": Role.STATE_ADMIN,
    "DIVISION_HEAD": Role.DIVISION_HEAD,
    "DISTRICT_COLLECTOR": Role.DISTRICT_COLLECTOR,
    "DIO_DESK": Role.DIO_DESK,

    # JWT / Spring / Enum formatted names
    "ROLE_DG_STATE_ADMIN": Role.STATE_ADMIN,
    "ROLE_STATE_ADMIN": Role.STATE_ADMIN,
    "ROLE_DIVISION_HEAD": Role.DIVISION_HEAD,
    "ROLE_DISTRICT_COLLECTOR": Role.DISTRICT_COLLECTOR,
    "ROLE_DIO_DESK": Role.DIO_DESK,
}


def to_role(raw: Optional[str]) -> Optional[Role]:
    """Convert raw role string to authoritative Role via exact match.

    Returns None for any unmapped or ambiguous role to fail closed.
    """
    if not raw or not isinstance(raw, str):
        return None
    return _EXACT_ROLE_MAP.get(raw.strip())
