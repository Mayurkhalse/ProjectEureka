"""Authoritative Permission Matrix and Scope Resolution for Nirdeshak Copilot.

Maps (Role x Intent) -> ScopeKind.
Defines explicit allowed district calculation and default district resolution.
"""

from enum import Enum
from typing import Mapping

from eureka.core.reference_data import DISTRICTS, DIVISIONS
from eureka.copilot.policy.roles import Role
from eureka.copilot.policy.principal import PolicyPrincipal, ALL_DISTRICT_CODES


class Intent(str, Enum):
    """Operation intent families."""
    PROFILE = "profile"
    PILLAR = "pillar"
    TREND = "trend"
    COMPARE = "compare"
    RUMORS = "rumors"
    FORECAST = "forecast"
    NEIGHBORS = "neighbors"
    LEAGUE = "league"
    DIVISION_ROLLUP = "division_rollup"
    DOSSIER = "dossier"


class ScopeKind(str, Enum):
    """Permitted scope boundaries for an intent."""
    NONE = "none"
    OWN_DISTRICT = "own_district"
    OWN_DIVISION = "own_division"
    STATEWIDE = "statewide"


# Single source of truth: Division to District codes derived from authoritative DISTRICTS
DIVISION_DISTRICT_MAP: dict[str, frozenset[str]] = {}
for div in DIVISIONS:
    div_code = div[0]
    div_name = div[1]
    dist_set = frozenset(d[0] for d in DISTRICTS if d[1] == div_code)
    DIVISION_DISTRICT_MAP[div_code] = dist_set
    DIVISION_DISTRICT_MAP[div_name] = dist_set
    DIVISION_DISTRICT_MAP[div_code.upper()] = dist_set
    DIVISION_DISTRICT_MAP[div_name.upper()] = dist_set


# The Authoritative Matrix (§5.3 of POLICYENGINE.md)
RULES: Mapping[Role, Mapping[Intent, ScopeKind]] = {
    Role.STATE_ADMIN: {
        Intent.PROFILE: ScopeKind.STATEWIDE,
        Intent.PILLAR: ScopeKind.STATEWIDE,
        Intent.TREND: ScopeKind.STATEWIDE,
        Intent.COMPARE: ScopeKind.STATEWIDE,
        Intent.RUMORS: ScopeKind.STATEWIDE,
        Intent.FORECAST: ScopeKind.STATEWIDE,
        Intent.NEIGHBORS: ScopeKind.STATEWIDE,
        Intent.LEAGUE: ScopeKind.STATEWIDE,
        Intent.DIVISION_ROLLUP: ScopeKind.STATEWIDE,
        Intent.DOSSIER: ScopeKind.STATEWIDE,
    },
    Role.DIVISION_HEAD: {
        Intent.PROFILE: ScopeKind.OWN_DIVISION,
        Intent.PILLAR: ScopeKind.OWN_DIVISION,
        Intent.TREND: ScopeKind.OWN_DIVISION,
        Intent.COMPARE: ScopeKind.OWN_DIVISION,
        Intent.RUMORS: ScopeKind.OWN_DIVISION,  # Fixes A5: strictly scoped to own division
        Intent.FORECAST: ScopeKind.OWN_DIVISION,
        Intent.NEIGHBORS: ScopeKind.OWN_DIVISION,
        Intent.LEAGUE: ScopeKind.OWN_DIVISION,
        Intent.DIVISION_ROLLUP: ScopeKind.OWN_DIVISION,
        Intent.DOSSIER: ScopeKind.OWN_DIVISION,
    },
    Role.DISTRICT_COLLECTOR: {
        Intent.PROFILE: ScopeKind.OWN_DISTRICT,
        Intent.PILLAR: ScopeKind.OWN_DISTRICT,
        Intent.TREND: ScopeKind.OWN_DISTRICT,
        Intent.COMPARE: ScopeKind.OWN_DISTRICT,
        Intent.RUMORS: ScopeKind.OWN_DISTRICT,
        Intent.FORECAST: ScopeKind.OWN_DISTRICT,
        Intent.NEIGHBORS: ScopeKind.OWN_DISTRICT,
        Intent.LEAGUE: ScopeKind.OWN_DISTRICT,
        Intent.DIVISION_ROLLUP: ScopeKind.NONE,  # Hard deny
        Intent.DOSSIER: ScopeKind.OWN_DISTRICT,
    },
    Role.DIO_DESK: {
        Intent.PROFILE: ScopeKind.OWN_DISTRICT,
        Intent.PILLAR: ScopeKind.OWN_DISTRICT,
        Intent.TREND: ScopeKind.OWN_DISTRICT,
        Intent.COMPARE: ScopeKind.OWN_DISTRICT,
        Intent.RUMORS: ScopeKind.OWN_DISTRICT,
        Intent.FORECAST: ScopeKind.OWN_DISTRICT,
        Intent.NEIGHBORS: ScopeKind.OWN_DISTRICT,
        Intent.LEAGUE: ScopeKind.OWN_DISTRICT,
        Intent.DIVISION_ROLLUP: ScopeKind.NONE,  # Hard deny
        Intent.DOSSIER: ScopeKind.OWN_DISTRICT,
    },
}


def allowed_districts(principal: PolicyPrincipal, scope_kind: ScopeKind) -> frozenset[str]:
    """Compute explicit set of allowed district codes for a principal under a scope kind."""
    if scope_kind == ScopeKind.STATEWIDE:
        return ALL_DISTRICT_CODES
    elif scope_kind == ScopeKind.OWN_DIVISION:
        if not principal.division:
            return frozenset()
        return DIVISION_DISTRICT_MAP.get(principal.division, frozenset())
    elif scope_kind == ScopeKind.OWN_DISTRICT:
        if not principal.district_code:
            return frozenset()
        return frozenset({principal.district_code})
    return frozenset()


def default_districts(principal: PolicyPrincipal, intent: Intent, scope_kind: ScopeKind) -> frozenset[str]:
    """Determine default district codes when an operation omitted explicit entities."""
    if principal.role in (Role.DISTRICT_COLLECTOR, Role.DIO_DESK):
        if principal.district_code:
            return frozenset({principal.district_code})
        return frozenset()
    elif principal.role == Role.DIVISION_HEAD:
        if intent in (Intent.RUMORS, Intent.LEAGUE, Intent.DIVISION_ROLLUP):
            return allowed_districts(principal, ScopeKind.OWN_DIVISION)
        return frozenset()
    elif principal.role == Role.STATE_ADMIN:
        if intent in (Intent.RUMORS, Intent.LEAGUE):
            return ALL_DISTRICT_CODES
        return frozenset()
    return frozenset()
