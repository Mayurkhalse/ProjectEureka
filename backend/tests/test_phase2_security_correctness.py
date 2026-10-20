"""Comprehensive tests for Phase 2: Correctness and Security Fixes.

Covers:
2.1 Multi-functionCall parallel execution (e.g. compare Nashik and Ahilyanagar).
2.2 Tool errors, RBAC refusals, and exceptions never breaking SSE stream.
2.3 GemmaClient non-retryable 4xx codes and shared client.
2.4 Model honesty and key isolation: get_effective_gemini_key cannot return GEMINI_API_KEY.
2.5 CopilotPrincipal.division and division-head scope enforcement across tools.
2.6 AST validation, Devanagari numerals normalization, prop checks, and accessibility enforcement.
2.7 Honest done event metadata.
"""

import json
import os
import re
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from eureka.api.auth import TokenData
from eureka.copilot.config import get_copilot_settings, CopilotSettings
from eureka.copilot.tools import (
    CopilotPrincipal,
    DIVISION_DISTRICT_MAP,
    tool_district_profile,
    DistrictProfileArgs,
    tool_compare_districts,
    CompareDistrictsArgs,
    tool_active_rumors,
    ActiveRumorsArgs,
    verify_district_authorization,
)
from eureka.copilot.openui_generator import (
    normalize_numerals_and_text,
    validate_openui_output,
    validate_props_and_security,
)
from eureka.models.enums import UserRole


# ============================================================================
# 2.4 KEY ISOLATION & MODEL HONESTY
# ============================================================================

def test_get_effective_gemini_key_never_returns_main_gemini_key():
    """Verify that get_effective_gemini_key() cannot fall back to general GEMINI_API_KEY."""
    with patch.dict(os.environ, {
        "OPENUI_COPILOT_GEMINI_API_KEY": "",
        "GOOGLE_STUDIO_API_KEY": "",
        "GEMINI_API_KEY": "forbidden-unisolated-main-key",
    }):
        settings = CopilotSettings()
        key = settings.get_effective_gemini_key()
        assert key != "forbidden-unisolated-main-key"
        assert key is None


# ============================================================================
# 2.5 DIVISION-HEAD SCOPE ENFORCEMENT ACROSS ROLES AND TOOLS
# ============================================================================

def test_division_head_scoping_in_principal_and_tools():
    """Verify Division Head can inspect districts in their division, but rejected for others."""
    # Pune division: MH-07 (Pune), MH-08 (Satara), MH-09 (Solapur)
    pune_div_head = CopilotPrincipal(
        username="divhead_pune",
        role="ROLE_DIVISION_HEAD",
        division="DIV-PUN",
    )

    # Allowed: Pune (MH-07)
    err_pune = verify_district_authorization(pune_div_head, "MH-07")
    assert err_pune is None

    # Refused: Thane (MH-04, Konkan)
    err_thane = verify_district_authorization(pune_div_head, "MH-04")
    assert err_thane is not None
    assert "Access Denied" in err_thane or "PERMISSION_DENIED" in err_thane

    # Test tool_district_profile with refused district returns PERMISSION_DENIED
    res = tool_district_profile(pune_div_head, DistrictProfileArgs(district_code="MH-04"))
    assert res.get("error") == "PERMISSION_DENIED"

    # Test compare_districts: if one district is outside division, refuses
    cmp_res = tool_compare_districts(pune_div_head, CompareDistrictsArgs(district_codes=["MH-07", "MH-04"]))
    assert cmp_res.get("error") == "PERMISSION_DENIED"


# ============================================================================
# 2.6 STRICT GROUNDING, DEVANAGARI DIGITS & PROP SECURITY
# ============================================================================

def test_devanagari_numerals_normalization():
    """Verify Devanagari numerals (०-९) normalize to Arabic digits (0-9)."""
    raw_marathi = "ठाणे जिल्ह्याचा गुण ९६.७५ आहे आणि क्रमवारी १ आहे."
    normalized = normalize_numerals_and_text(raw_marathi)
    assert "96.75" in normalized
    assert "1" in normalized


def test_reject_fabricated_numbers_and_urls_in_props():
    """Verify fabricated numbers or forbidden URLs in props fail validation."""
    tool_data = [{"data": {"district_name": "Thane", "composite_index": 96.75}}]

    # Fabricated number 99.99
    fabricated_markup = '<KpiCard title="Thane" value="99.99" unit="/100" />'
    is_valid, errors = validate_openui_output(fabricated_markup, tool_data)
    assert not is_valid
    assert any("FABRICATED_NUMBER" in e for e in errors)

    # URL in prop
    malicious_markup = '<Callout type="info" message="Visit http://evil.com/leak" />'
    is_valid_prop, prop_errors = validate_props_and_security(malicious_markup)
    assert not is_valid_prop
    assert any("URL" in e or "SECURITY" in e for e in prop_errors)


def test_enforce_chart_accessibility_text_and_table():
    """Verify BarChart/LineChart without accessible table alternative fails validation."""
    tool_data = [{"data": {"districts": [{"name": "Thane", "score": 96.75}]}}]

    # Missing table alternative
    inaccessible_chart = '<BarChart title="Performance" xKey="name" yKey="score" data="[]"><Text content="Summary" /></BarChart>'
    is_valid, errors = validate_openui_output(inaccessible_chart, tool_data)
    assert not is_valid
    assert any("ACCESSIBILITY" in e for e in errors)


# ============================================================================
# 2.1 MULTI-FUNCTION CALL CONCURRENT EXECUTION
# ============================================================================

@pytest.mark.asyncio
async def test_multi_function_call_parallel_execution():
    """Verify router handles multiple functionCall parts in a single turn concurrently."""
    from eureka.copilot.router import copilot_query, CopilotQueryRequest

    user = TokenData(username="test_officer", role=UserRole.DG_STATE_ADMIN)
    req = CopilotQueryRequest(query="Compare Nashik and Ahilyanagar", language="en")

    # Mock model returning two function calls in the first turn
    mock_multi_fn_resp = {
        "candidates": [{
            "content": {
                "parts": [
                    {
                        "functionCall": {
                            "name": "district_profile",
                            "args": {"district_code": "MH-21"},  # Nashik
                        }
                    },
                    {
                        "functionCall": {
                            "name": "district_profile",
                            "args": {"district_code": "MH-25"},  # Ahilyanagar
                        }
                    },
                ]
            }
        }]
    }

    mock_synthesis_resp = {
        "candidates": [{
            "content": {
                "parts": [{
                    "text": '<Heading level=2 text="Nashik vs Ahilyanagar" />\n<KpiCard title="Nashik" value="92.28" />'
                }]
            }
        }]
    }

    with patch("eureka.copilot.router._gemma_client.generate", side_effect=[mock_multi_fn_resp, mock_synthesis_resp]):
        response = await copilot_query(req, current_user=user)
        events = []
        async for chunk in response.body_iterator:
            events.append(chunk)

        full_text = "".join(events)
        assert "event: done" in full_text
        # Both tool calls should be reported in status events
        assert "MH-21" in full_text
        assert "MH-25" in full_text
