"""Fail-Closed Security and Boundary Invariant Tests (§14.2 of POLICYENGINE.md)."""

import pytest
from eureka.copilot.policy.principal import PolicyPrincipal, build_principal, PrincipalError
from eureka.copilot.policy.roles import Role
from eureka.copilot.policy.decisions import Scope, AuthorizedOp, POLICY_VERSION
from eureka.copilot.policy.scope_filter import filter_result, ScopeFilterError
from eureka.copilot.planning.plan import Op
from eureka.copilot.policy.matrix import Intent


def test_authorized_op_sealed_against_unauthorized_instantiation():
    op = Op(op_id="o1", intent=Intent.PROFILE, tool="district_profile", args={"district_code": "MH-01"}, districts=("MH-01",), group="g1", label="L1")
    scope = Scope(frozenset({"MH-01"}))

    # Constructing AuthorizedOp without internal _SEAL must raise PermissionError
    with pytest.raises(PermissionError):
        AuthorizedOp(op=op, scope=scope, decision_id="d1", policy_version=POLICY_VERSION)


def test_scope_filter_removes_unauthorized_records():
    scope = Scope(frozenset({"MH-21"}))

    # League table data containing multiple districts
    raw_league = {
        "districts": [
            {"district_code": "MH-21", "name_en": "Nashik", "composite_index": 82.5},
            {"district_code": "MH-04", "name_en": "Thane", "composite_index": 79.1},
            {"district_code": "MH-23", "name_en": "Dhule", "composite_index": 68.4},
        ],
        "total_count": 3,
    }

    filtered = filter_result("league_table", raw_league, scope)
    assert len(filtered["districts"]) == 1
    assert filtered["districts"][0]["district_code"] == "MH-21"


def test_scope_filter_fails_closed_on_unrecognized_structure():
    scope = Scope(frozenset({"MH-21"}))
    corrupt_data = {"unexpected_key": [1, 2, 3]}

    with pytest.raises(ScopeFilterError):
        filter_result("league_table", corrupt_data, scope)


def test_scope_filter_blocks_single_district_leakage():
    scope = Scope(frozenset({"MH-21"}))
    profile_data = {
        "district_code": "MH-04",  # Unauthorized district
        "name_en": "Thane",
        "composite_index": 79.1,
    }

    with pytest.raises(ScopeFilterError):
        filter_result("district_profile", profile_data, scope)
