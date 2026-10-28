"""Comprehensive tests for vague, conversational, and multilingual queries.

Ensures:
1. Vague conversational queries decompose accurately into governed tools.
2. Specific district queries NEVER spuriously inject the statewide 36-district league table.
3. Explicit statewide queries (leaderboards, rankings) correctly invoke league_table.
4. Explanations for low/high rank and crisis SLA are numerically grounded.
5. Headings and cards use human-readable district names (e.g. 'Nashik · Active Rumors').
"""

import pytest
from eureka.copilot.planning.parser import parse_query
from eureka.copilot.policy.principal import PolicyPrincipal
from eureka.copilot.policy.roles import Role
from eureka.copilot.router import copilot_query, CopilotQueryRequest
from eureka.api.auth import TokenData
from eureka.models.enums import UserRole


@pytest.fixture
def admin_principal():
    return PolicyPrincipal(username="dg_admin", role=Role.STATE_ADMIN)


# ==============================================================================
# 15 Vague & Conversational Query Decompositions
# ==============================================================================

def test_vague_query_1_nashik_crisis_no_league_table():
    q = "What is Nashik Crisis score and why is it like that"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "active_rumors" in tools
    assert "pillar_breakdown" in tools
    assert any(op.args.get("pillar_name") == "crisis_sla" for op in res.ops)
    assert any(op.districts == ("MH-21",) for op in res.ops)


def test_vague_query_2_dhule_rank_explanation():
    q = "why is dhule at this rank it should explain too"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "district_profile" in tools
    prof_op = next(op for op in res.ops if op.tool == "district_profile")
    assert prof_op.districts == ("MH-23",)


def test_vague_query_3_pune_general_status():
    q = "how is Pune doing lately"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "district_profile" in tools
    assert any(op.districts == ("MH-07",) for op in res.ops)


def test_vague_query_4_solapur_sentiment():
    q = "what do people think in Solapur"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "pillar_breakdown" in tools
    assert any(op.args.get("pillar_name") == "sentiment" for op in res.ops)
    assert any(op.districts == ("MH-09",) for op in res.ops)


def test_vague_query_5_palghar_fake_news():
    q = "any fake news in Palghar right now"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "active_rumors" in tools
    assert any(op.districts == ("MH-03",) for op in res.ops)


def test_vague_query_6_thane_news_volume():
    q = "news coverage of Thane"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "pillar_breakdown" in tools
    assert any(op.args.get("pillar_name") == "volume" for op in res.ops)
    assert any(op.districts == ("MH-04",) for op in res.ops)


def test_vague_query_7_washim_bottom_rank():
    q = "why is Washim at the bottom"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "district_profile" in tools
    assert any(op.districts == ("MH-28",) for op in res.ops)


def test_vague_query_8_compare_nashik_ahilyanagar():
    q = "compare Nashik and Ahilyanagar"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "compare_districts" in tools
    cmp_op = next(op for op in res.ops if op.tool == "compare_districts")
    assert "MH-21" in cmp_op.districts
    assert "MH-25" in cmp_op.districts


def test_vague_query_9_leaderboard_explicit():
    q = "who is leading the state leaderboard"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" in tools


def test_vague_query_10_top_5_statewide():
    q = "top 5 districts in Maharashtra"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" in tools


def test_vague_query_11_marathi_pune_situation():
    q = "पुण्याची परिस्थिती कशी आहे"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "district_profile" in tools
    assert any(op.districts == ("MH-07",) for op in res.ops)


def test_vague_query_12_marathi_dhule_score_drop():
    q = "धुळ्याचा स्कोर का कमी झाला"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "district_profile" in tools
    assert any(op.districts == ("MH-23",) for op in res.ops)


def test_vague_query_13_hindi_nashik_status():
    q = "नासिक में क्या चल रहा है"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "district_profile" in tools
    assert any(op.districts == ("MH-21",) for op in res.ops)


def test_vague_query_14_beed_neighbors():
    q = "border districts of Beed"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "neighbors" in tools
    assert any(op.districts == ("MH-20",) for op in res.ops)


def test_vague_query_15_nashik_division_overall():
    q = "how is Nashik division performing overall"
    res = parse_query(q)
    tools = [op.tool for op in res.ops]
    assert "league_table" not in tools
    assert "division_rollup" in tools
    assert res.ops[0].args.get("division_code") == "DIV-NSK"


# ==============================================================================
# End-to-End Execution & Output Grounding Verifications
# ==============================================================================

@pytest.mark.asyncio
async def test_e2e_nashik_crisis_no_leaderboard_in_markup():
    user = TokenData(username="test_admin", role=UserRole.DG_STATE_ADMIN)
    req = CopilotQueryRequest(query="What is Nashik Crisis score and why is it like that", language="en")
    resp = await copilot_query(req, current_user=user)

    chunks = []
    async for chunk in resp.body_iterator:
        if "event: chunk" in chunk:
            chunks.append(chunk)

    full_output = "".join(chunks)

    # 1. Must NOT contain the 36-district leaderboard
    assert "Maharashtra District Governance Leaderboard" not in full_output
    assert "League Table" not in full_output

    # 2. Must contain Nashik crisis analysis & active rumors
    assert "Crisis SLA Analysis" in full_output
    assert "Nashik" in full_output
    assert "27.27" in full_output
    assert "Active Crisis Rumors" in full_output

    # 3. Must use human-readable district name in heading
    assert "Active Rumors" in full_output
    assert "MH-21 \\u00b7 Active Rumors" not in full_output and "MH-21 · Active Rumors" not in full_output


@pytest.mark.asyncio
async def test_e2e_dhule_rank_explanation_grounding():
    user = TokenData(username="test_admin", role=UserRole.DG_STATE_ADMIN)
    req = CopilotQueryRequest(query="why is dhule at this rank it should explain too", language="en")
    resp = await copilot_query(req, current_user=user)

    chunks = []
    async for chunk in resp.body_iterator:
        if "event: chunk" in chunk:
            chunks.append(chunk)

    full_output = "".join(chunks)

    # 1. Must NOT contain the full 36-district leaderboard
    assert "Maharashtra District Governance Leaderboard" not in full_output

    # 2. Must explain Dhule's rank #31 of 36
    assert "#31" in full_output
    assert "59.27" in full_output
    assert "Crisis SLA" in full_output


@pytest.mark.asyncio
async def test_e2e_disjoint_multi_intent_nashik_crisis_dhule_sentiment():
    user = TokenData(username="test_admin", role=UserRole.DG_STATE_ADMIN)
    req = CopilotQueryRequest(query="Crisis sla of Nashik and Sentiment score of Dhule", language="en")
    resp = await copilot_query(req, current_user=user)

    chunks = []
    async for chunk in resp.body_iterator:
        if "event: chunk" in chunk:
            chunks.append(chunk)

    full_output = "".join(chunks)

    # 1. Nashik: MUST contain Crisis SLA Analysis and Nashik Active Rumors
    assert "Crisis SLA Analysis" in full_output
    assert "Nashik" in full_output
    assert "Active Rumors" in full_output

    # 2. Dhule: MUST contain Dhule Sentiment Analysis
    assert "Dhule" in full_output
    assert "Sentiment Analysis" in full_output
    assert "24.67" in full_output

    # 3. Disjoint Isolation: MUST NOT cross-pollinate
    assert "Dhule \\u2014 Crisis SLA Analysis" not in full_output and "Dhule — Crisis SLA Analysis" not in full_output
    assert "Nashik \\u2014 Sentiment Analysis" not in full_output and "Nashik — Sentiment Analysis" not in full_output
    assert "Dhule \\u00b7 Active Rumors" not in full_output and "Dhule · Active Rumors" not in full_output

