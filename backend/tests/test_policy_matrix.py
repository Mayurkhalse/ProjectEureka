"""Authoritative Policy Matrix and Permission Boundary Tests (§14.1 of POLICYENGINE.md)."""

import pytest
from eureka.copilot.policy.roles import Role, to_role
from eureka.copilot.policy.principal import PolicyPrincipal, build_principal, PrincipalError
from eureka.copilot.policy.matrix import Intent, ScopeKind, RULES, allowed_districts
from eureka.copilot.policy.decisions import Verdict, Reason, Scope, AuthorizedOp, POLICY_VERSION
from eureka.copilot.policy.engine import decide, authorize_plan, PlanContext
from eureka.copilot.planning.plan import Op, Plan


class MockSettings:
    COPILOT_MAX_OPS = 6
    COPILOT_DEMO_MODE = False


class MockDemoSettings:
    COPILOT_MAX_OPS = 6
    COPILOT_DEMO_MODE = True


def test_role_exact_matching():
    assert to_role("DG State Admin") == Role.STATE_ADMIN
    assert to_role("District Collector") == Role.DISTRICT_COLLECTOR
    assert to_role("DIO Desk") == Role.DIO_DESK
    assert to_role("Division Head") == Role.DIVISION_HEAD
    # Substring matches must fail closed
    assert to_role("admin") is None
    assert to_role("collector") is None
    assert to_role("super_admin") is None
    assert to_role("Director Konkan") is None


def test_principal_validation():
    # Collector requires district
    p_coll = build_principal({"username": "coll_nsk", "role": "District Collector", "district_code": "MH-21"})
    assert p_coll.role == Role.DISTRICT_COLLECTOR
    assert p_coll.district_code == "MH-21"
    assert p_coll.division == "Nashik"

    # Collector without district raises PrincipalError
    with pytest.raises(PrincipalError):
        build_principal({"username": "coll_bad", "role": "District Collector"})

    # Division head requires division
    p_div = build_principal({"username": "div_head", "role": "Division Head"}, division_claim="DIV-NSK")
    assert p_div.role == Role.DIVISION_HEAD
    assert p_div.division == "Nashik"

    with pytest.raises(PrincipalError):
        build_principal({"username": "div_bad", "role": "Division Head"})


def test_policy_matrix_hand_written_expectations():
    settings = MockSettings()
    ctx = PlanContext()

    p_coll_nsk = PolicyPrincipal(username="coll_nsk", role=Role.DISTRICT_COLLECTOR, district_code="MH-21", division="Nashik")
    p_div_nsk = PolicyPrincipal(username="div_nsk", role=Role.DIVISION_HEAD, district_code=None, division="Nashik")
    p_admin = PolicyPrincipal(username="admin", role=Role.STATE_ADMIN, district_code=None, division=None)
    p_dio_dhl = PolicyPrincipal(username="dio_dhl", role=Role.DIO_DESK, district_code="MH-23", division="Nashik")

    # 1. Collector Nashik on own district -> ALLOW
    op1 = Op(op_id="o1", intent=Intent.PILLAR, tool="pillar_breakdown", args={"district_code": "MH-21"}, districts=("MH-21",), group="g1", label="L1")
    d1 = decide(p_coll_nsk, op1, ctx, settings)
    assert d1.verdict == Verdict.ALLOW
    assert d1.reason == Reason.OK
    assert d1.scope == Scope(frozenset({"MH-21"}))

    # 2. Collector Nashik on Dhule (MH-23) -> DENY DISTRICT_OUT_OF_SCOPE
    op2 = Op(op_id="o2", intent=Intent.PILLAR, tool="pillar_breakdown", args={"district_code": "MH-23"}, districts=("MH-23",), group="g2", label="L2")
    d2 = decide(p_coll_nsk, op2, ctx, settings)
    assert d2.verdict == Verdict.DENY
    assert d2.reason == Reason.DISTRICT_OUT_OF_SCOPE

    # 3. Collector Nashik compare(MH-21, MH-04) -> DENY whole op
    op3 = Op(op_id="o3", intent=Intent.COMPARE, tool="compare_districts", args={"district_codes": ["MH-21", "MH-04"]}, districts=("MH-21", "MH-04"), group="g3", label="L3")
    d3 = decide(p_coll_nsk, op3, ctx, settings)
    assert d3.verdict == Verdict.DENY
    assert d3.reason == Reason.DISTRICT_OUT_OF_SCOPE

    # 4. Collector Nashik division_rollup -> DENY ROLE_NOT_PERMITTED
    op4 = Op(op_id="o4", intent=Intent.DIVISION_ROLLUP, tool="division_rollup", args={"division": "Nashik"}, districts=(), group="g4", label="L4")
    d4 = decide(p_coll_nsk, op4, ctx, settings)
    assert d4.verdict == Verdict.DENY
    assert d4.reason == Reason.ROLE_NOT_PERMITTED

    # 5. Collector Nashik rumors without explicit district -> ALLOW, scope = {MH-21}
    op5 = Op(op_id="o5", intent=Intent.RUMORS, tool="active_rumors", args={}, districts=(), group="g5", label="L5", defaulted_scope=True)
    d5 = decide(p_coll_nsk, op5, ctx, settings)
    assert d5.verdict == Verdict.ALLOW
    assert d5.scope == Scope(frozenset({"MH-21"}))

    # 6. Division Head Nashik rumors without district -> ALLOW, scope = Nashik division only (fixes A5)
    d6 = decide(p_div_nsk, op5, ctx, settings)
    assert d6.verdict == Verdict.ALLOW
    assert d6.scope == Scope(frozenset({"MH-21", "MH-22", "MH-23", "MH-24", "MH-25"}))

    # 7. Division Head Nashik on Thane (MH-04 in Konkan) -> DENY DISTRICT_OUT_OF_SCOPE
    op7 = Op(op_id="o7", intent=Intent.PILLAR, tool="pillar_breakdown", args={"district_code": "MH-04"}, districts=("MH-04",), group="g7", label="L7")
    d7 = decide(p_div_nsk, op7, ctx, settings)
    assert d7.verdict == Verdict.DENY
    assert d7.reason == Reason.DISTRICT_OUT_OF_SCOPE

    # 8. State Admin -> ALLOW statewide
    d8 = decide(p_admin, op7, ctx, settings)
    assert d8.verdict == Verdict.ALLOW

    # 9. Trend outside demo mode -> DENY SOURCE_NOT_AVAILABLE (§7.4)
    op9 = Op(op_id="o9", intent=Intent.TREND, tool="trend", args={"district_code": "MH-21"}, districts=("MH-21",), group="g9", label="L9")
    d9_prod = decide(p_coll_nsk, op9, ctx, settings)
    assert d9_prod.verdict == Verdict.DENY
    assert d9_prod.reason == Reason.SOURCE_NOT_AVAILABLE

    # 10. Trend inside demo mode -> ALLOW (§7.4)
    d9_demo = decide(p_coll_nsk, op9, ctx, MockDemoSettings())
    assert d9_demo.verdict == Verdict.ALLOW


def test_authorize_plan_limits():
    settings = MockSettings()
    p = PolicyPrincipal(username="admin", role=Role.STATE_ADMIN, district_code=None, division=None)

    ops = [
        Op(op_id=f"o{i}", intent=Intent.PROFILE, tool="district_profile", args={"district_code": "MH-01"}, districts=("MH-01",), group=f"g{i}", label=f"L{i}")
        for i in range(1, 9)  # 8 ops, limit is 6
    ]
    plan = Plan(ops=tuple(ops))
    decision = authorize_plan(p, plan, settings)

    assert len(decision.allowed) == 6
    assert len(decision.denied) == 2
    assert decision.denied[0].reason == Reason.LIMIT_EXCEEDED
