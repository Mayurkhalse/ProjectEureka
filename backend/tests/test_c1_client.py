"""Tests for Thesys C1 Generative UI Client & Pipeline Integration."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from eureka.copilot.config import get_copilot_settings


def test_c1_settings_and_defaults():
    """Verify C1 settings exist with safe defaults and correct base URL."""
    settings = get_copilot_settings()
    assert hasattr(settings, "COPILOT_UI_ENGINE")
    assert hasattr(settings, "C1_MODEL_ID")
    assert settings.C1_BASE_URL == "https://api.thesys.dev/v1/embed"
    assert settings.C1_MODEL_ID == "c1-20250416"


@pytest.mark.asyncio
async def test_c1_client_generate_ui_mocked():
    """Verify C1Client calls AsyncOpenAI with custom component schemas and quoted data."""
    from eureka.copilot.c1_client import C1Client

    mock_client = AsyncMock()
    mock_completion = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = '<KpiCard title="Thane Governance" value="96.75" unit="/100" />'
    mock_completion.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_completion

    c1 = C1Client(api_key="test-c1-key")
    c1._openai_client = mock_client

    sample_tool_data = {
        "district_code": "MH-04",
        "district_name": "Thane",
        "composite_index": 96.75,
    }

    result = await c1.generate_ui(
        tool_name="district_profile",
        tool_data=sample_tool_data,
        user_query="How is Thane performing?",
        language="en",
    )

    assert "<KpiCard" in result
    assert "96.75" in result
    mock_client.chat.completions.create.assert_called_once()
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "c1-20250416"
    assert "messages" in call_kwargs


@pytest.mark.asyncio
async def test_c1_client_circuit_breaker():
    """Verify C1Client circuit breaker trips after repeated failures."""
    from eureka.copilot.c1_client import C1Client, C1CircuitBreakerOpen

    c1 = C1Client(api_key="test-c1-key")
    mock_client = AsyncMock()
    mock_client.chat.completions.create.side_effect = RuntimeError("503 Service Unavailable")
    c1._openai_client = mock_client

    # Trigger threshold failures
    for _ in range(5):
        try:
            await c1.generate_ui("league_table", {}, "query")
        except Exception:
            pass

    # Next call should be blocked by circuit breaker
    with pytest.raises(C1CircuitBreakerOpen):
        await c1.generate_ui("league_table", {}, "query")


def test_c1_custom_components_schema():
    """Verify custom components registered with C1 match MCC canonical library."""
    from eureka.copilot.c1_client import get_c1_custom_components

    components = get_c1_custom_components()
    comp_names = {c["name"] for c in components}
    expected = {"KpiCard", "DataTable", "BarChart", "LineChart", "GraphView", "Callout", "Heading"}
    assert expected.issubset(comp_names)


@pytest.mark.asyncio
async def test_c1_router_integration_fallback_on_error():
    """Verify that router with COPILOT_UI_ENGINE=c1 gracefully falls back to deterministic ViewSpec on C1 error."""
    import json
    import re
    from eureka.api.auth import TokenData
    from eureka.copilot.router import copilot_query, CopilotQueryRequest
    from eureka.models.enums import UserRole

    user = TokenData(username="test_officer", role=UserRole.DG_STATE_ADMIN)
    req = CopilotQueryRequest(query="Show top 5 districts", language="en")

    with patch.dict(os.environ, {"COPILOT_UI_ENGINE": "c1"}), \
         patch("eureka.copilot.router.get_copilot_settings", return_value=get_copilot_settings().__class__(COPILOT_UI_ENGINE="c1")), \
         patch("eureka.copilot.c1_client.C1Client.generate_ui", side_effect=RuntimeError("Insufficient balance")):
        response = await copilot_query(req, current_user=user)
        events = []
        async for chunk in response.body_iterator:
            events.append(chunk)

        full_text = "".join(events)
        assert "event: done" in full_text
        done_match = re.search(r"event: done\ndata: (\{.*\})", full_text)
        assert done_match is not None
        done_data = json.loads(done_match.group(1))
        assert done_data["fallback"] is True
        assert "timings" in done_data
        assert "c1_ms" in done_data["timings"]


@pytest.mark.asyncio
async def test_c1_router_successful_c1_markup():
    """Verify that router with COPILOT_UI_ENGINE=c1 successfully emits C1 markup when valid."""
    import json
    import re
    from eureka.api.auth import TokenData
    from eureka.copilot.router import copilot_query, CopilotQueryRequest
    from eureka.models.enums import UserRole

    user = TokenData(username="test_officer", role=UserRole.DG_STATE_ADMIN)
    req = CopilotQueryRequest(query="top 5 districts by governance score", language="en")

    c1_valid_markup = (
        '<Heading level=2 text="Top 5 Maharashtra Districts" />\n'
        '<KpiCard title="Thane" value="95.45" unit="/100" />'
    )

    with patch.dict(os.environ, {"COPILOT_UI_ENGINE": "c1"}), \
         patch("eureka.copilot.router.get_copilot_settings", return_value=get_copilot_settings().__class__(COPILOT_UI_ENGINE="c1")), \
         patch("eureka.copilot.c1_client.C1Client.generate_ui", return_value=c1_valid_markup):
        response = await copilot_query(req, current_user=user)
        events = []
        async for chunk in response.body_iterator:
            events.append(chunk)

        full_text = "".join(events)
        assert "event: done" in full_text
        done_match = re.search(r"event: done\ndata: (\{.*\})", full_text)
        assert done_match is not None
        done_data = json.loads(done_match.group(1))
        assert done_data["engine"] == "c1"
        assert done_data["fallback"] is False
        assert done_data["model_id"] == "c1-20250416"
        assert "timings" in done_data
        assert "c1_ms" in done_data["timings"]
