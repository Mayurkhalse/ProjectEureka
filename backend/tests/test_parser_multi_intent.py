"""Unit tests for deterministic parser and multi-intent query decomposition (§14.3 of POLICYENGINE.md)."""

from eureka.copilot.planning.parser import parse_query
from eureka.copilot.policy.roles import Role
from eureka.copilot.policy.principal import PolicyPrincipal


def test_crisis_and_sentiment_dhule():
    query = "crisis and sentiment analysis of dhule"
    parsed = parse_query(query)

    assert parsed.confidence >= 0.7
    assert len(parsed.ops) == 3

    tool_intents = [(op.tool, op.intent.value) for op in parsed.ops]
    assert ("active_rumors", "rumors") in tool_intents
    assert ("pillar_breakdown", "pillar") in tool_intents

    # Verify Dhule (MH-23)
    for op in parsed.ops:
        assert op.districts == ("MH-23",)

    # Verify grouping
    assert any(op.args.get("pillar_name") == "crisis_sla" for op in parsed.ops)
    assert any(op.args.get("pillar_name") == "sentiment" for op in parsed.ops)


def test_compare_nashik_and_thane_and_show_rumors():
    query = "compare nashik and thane and show rumors"
    parsed = parse_query(query)

    assert parsed.confidence >= 0.7
    tools = [op.tool for op in parsed.ops]
    assert "compare_districts" in tools
    assert tools.count("active_rumors") == 2

    cmp_op = next(op for op in parsed.ops if op.tool == "compare_districts")
    assert "MH-21" in cmp_op.districts
    assert "MH-04" in cmp_op.districts


def test_marathi_crisis_and_sentiment():
    query = "धुळे संकट आणि भावना विश्लेषण"
    parsed = parse_query(query)

    assert len(parsed.ops) == 3
    for op in parsed.ops:
        assert op.districts == ("MH-23",)


def test_hindi_crisis_and_sentiment():
    query = "धुले संकट और भावना विश्लेषण"
    parsed = parse_query(query)

    assert len(parsed.ops) == 3
    for op in parsed.ops:
        assert op.districts == ("MH-23",)


def test_division_entity_does_not_preempt_district():
    query = "profile of pune division"
    parsed = parse_query(query)

    assert len(parsed.ops) == 1
    assert parsed.ops[0].tool == "division_rollup"
    assert parsed.ops[0].args.get("division_code") == "DIV-PUN"


def test_homonym_guard_police_thane():
    query = "पोलीस ठाणे मध्ये अफवा"
    parsed = parse_query(query)

    # Must NOT match Thane (MH-04)
    for op in parsed.ops:
        assert "MH-04" not in op.districts


def test_compare_needs_two_districts():
    query = "compare nashik"
    parsed = parse_query(query)

    assert len(parsed.ops) == 0
    assert "compare_needs_two_districts" in parsed.clarifications


def test_possessive_my_district():
    p = PolicyPrincipal(username="coll_nsk", role=Role.DISTRICT_COLLECTOR, district_code="MH-21", division="Nashik")
    query = "sentiment of my district"
    parsed = parse_query(query, principal=p)

    assert len(parsed.ops) == 1
    assert parsed.ops[0].districts == ("MH-21",)
    assert parsed.ops[0].defaulted_scope is True


def test_disjoint_multi_intent_crisis_nashik_and_sentiment_dhule():
    query = "Crisis sla of Nashik and Sentiment score of Dhule"
    parsed = parse_query(query)

    assert len(parsed.ops) == 3
    
    # 1. Nashik ops: rumors + crisis_sla only (NO sentiment)
    nsk_ops = [op for op in parsed.ops if op.districts == ("MH-21",)]
    assert len(nsk_ops) == 2
    assert any(op.tool == "active_rumors" for op in nsk_ops)
    assert any(op.tool == "pillar_breakdown" and op.args.get("pillar_name") == "crisis_sla" for op in nsk_ops)
    assert not any(op.tool == "pillar_breakdown" and op.args.get("pillar_name") == "sentiment" for op in nsk_ops)

    # 2. Dhule ops: sentiment only (NO rumors, NO crisis_sla)
    dhl_ops = [op for op in parsed.ops if op.districts == ("MH-23",)]
    assert len(dhl_ops) == 1
    assert dhl_ops[0].tool == "pillar_breakdown"
    assert dhl_ops[0].args.get("pillar_name") == "sentiment"


def test_disjoint_multi_intent_marathi():
    query = "नाशिकमधील संकट आणि धुळ्यातील जनभावना"
    parsed = parse_query(query)

    assert len(parsed.ops) == 3
    nsk_ops = [op for op in parsed.ops if op.districts == ("MH-21",)]
    assert len(nsk_ops) == 2
    dhl_ops = [op for op in parsed.ops if op.districts == ("MH-23",)]
    assert len(dhl_ops) == 1
    assert dhl_ops[0].args.get("pillar_name") == "sentiment"


def test_disjoint_multi_intent_hindi():
    query = "नासिक का क्राइसिस और धुले का सेंटिमेंट"
    parsed = parse_query(query)

    assert len(parsed.ops) == 3
    nsk_ops = [op for op in parsed.ops if op.districts == ("MH-21",)]
    assert len(nsk_ops) == 2
    dhl_ops = [op for op in parsed.ops if op.districts == ("MH-23",)]
    assert len(dhl_ops) == 1
    assert dhl_ops[0].args.get("pillar_name") == "sentiment"

