"""Targeted tests for fast-path deterministic router and latency optimizations."""

import json
import re
import pytest
from unittest.mock import patch

from eureka.api.auth import TokenData
from eureka.copilot.router import copilot_query, CopilotQueryRequest
from eureka.copilot.intent_router import match_fast_path
from eureka.copilot.tools import CopilotPrincipal
from eureka.models.enums import UserRole


def test_intent_router_recognizes_all_canonical_intents():
    principal = CopilotPrincipal(username="dg_admin", role="ROLE_DG_STATE_ADMIN")

    # 1. Leaderboard / League Table
    match_lt = match_fast_path("top 5 districts by governance score", principal)
    assert match_lt is not None
    assert match_lt[0] == "league_table"

    # 2. Compare
    match_cmp = match_fast_path("compare Nashik and Ahilyanagar", principal)
    assert match_cmp is not None
    assert match_cmp[0] == "compare_districts"
    assert "MH-21" in match_cmp[1]["district_codes"]
    assert "MH-25" in match_cmp[1]["district_codes"]

    # 3. Active Rumors
    match_rumor = match_fast_path("show active rumors for Pune", principal)
    assert match_rumor is not None
    assert match_rumor[0] == "active_rumors"

    # 4. District Profile
    match_prof = match_fast_path("how many news are there about thane", principal)
    assert match_prof is not None
    assert match_prof[0] == "district_profile"
    assert match_prof[1]["district_code"] == "MH-04"

    # 5. Marathi Query
    match_mr = match_fast_path("ठाणे जिल्ह्यातील कामगिरी", principal)
    assert match_mr is not None
    assert match_mr[0] == "district_profile"
    assert match_mr[1]["district_code"] == "MH-04"


@pytest.mark.asyncio
async def test_fast_path_emits_immediate_view_event():
    user = TokenData(username="test_officer", role=UserRole.DG_STATE_ADMIN)
    req = CopilotQueryRequest(query="top 5 districts by governance score", language="en")

    response = await copilot_query(req, current_user=user)
    events = []
    async for chunk in response.body_iterator:
        events.append(chunk)

    full_text = "".join(events)
    # Status event sent immediately
    assert "event: status" in full_text
    # Fast-path chunk emitted
    assert 'provenance": "fast_path"' in full_text
    # Done event emitted
    assert "event: done" in full_text
    done_match = re.search(r"event: done\ndata: (\{.*\})", full_text)
    assert done_match is not None
    done_data = json.loads(done_match.group(1))
    assert done_data["source_status"] in ("live", "demo")
    assert "timings" in done_data
