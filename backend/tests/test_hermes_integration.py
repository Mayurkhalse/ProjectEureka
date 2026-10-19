"""Comprehensive tests for Hermes Agent API Server integration, guardrails, and orchestrator.

Validates:
1. HermesClient HTTP API Server interactions (mocked /health, /v1/capabilities, /v1/chat/completions, /v1/responses).
2. Header semantics: Authorization Bearer, X-Hermes-Session-Id, X-Hermes-Session-Key, Idempotency-Key.
3. Structured error handling: HermesUnavailableError, HermesTimeoutError, HermesAPIError (409 conflict).
4. Strict Agent Autonomy Boundary: Autonomous sign-off forbidden; drafting & staging allowlisted.
5. Truthful execution reporting: Never fakes Hermes running when fallback executes.
6. FastAPI endpoints: GET /api/v1/hermes/health and POST /api/v1/hermes/execute guardrails.
7. Opt-in live test against active Hermes daemon (if online).
"""

import json
import os
import shutil
from unittest.mock import MagicMock, patch
import httpx
import pytest
from fastapi.testclient import TestClient

from eureka.api.auth import create_access_token
from eureka.api.main import app
from eureka.hermes.agent_tools import (
    AGENT_ALLOWLISTED_TOOLS,
    AGENT_TOOL_DEFINITIONS,
    AGENT_TOOL_MAP,
    tool_stage_dm_rebuttal,
)
from eureka.hermes.hermes_client import (
    HermesAPIError,
    HermesClient,
    HermesTimeoutError,
    HermesUnavailableError,
)
from eureka.hermes.orchestrator import HermesOrchestrator
from eureka.models.enums import UserRole


@pytest.fixture
def client():
    return TestClient(app)


# --- 1. HermesClient Mocked Unit Tests ---

def test_hermes_client_headers():
    client = HermesClient(
        base_url="http://127.0.0.1:8642",
        api_key="test-secret-token-16chars",
    )
    headers = client._get_headers(
        session_id="sess-123",
        session_key="key-abc",
        idempotency_key="idem-456",
    )
    assert headers["Authorization"] == "Bearer test-secret-token-16chars"
    assert headers["X-Hermes-Session-Id"] == "sess-123"
    assert headers["X-Hermes-Session-Key"] == "key-abc"
    assert headers["Idempotency-Key"] == "idem-456"
    assert headers["Content-Type"] == "application/json"


def test_hermes_client_health_check_online():
    client = HermesClient(base_url="http://127.0.0.1:8642")
    mock_resp = MagicMock()
    mock_resp.status_code = 200

    with patch("httpx.Client.get", return_value=mock_resp):
        res = client.check_health()
        assert res["status"] == "online"
        assert res["http_code"] == 200


def test_hermes_client_health_check_offline():
    client = HermesClient(base_url="http://127.0.0.1:8642")

    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Connection refused")):
        res = client.check_health()
        assert res["status"] == "offline"
        assert "Connection refused" in res["error"]


def test_hermes_client_chat_completions_success():
    client = HermesClient(base_url="http://127.0.0.1:8642", api_key="secret-bearer-token")
    mock_payload = {
        "id": "chatcmpl-test-001",
        "object": "chat.completion",
        "model": "hermes-agent",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Official factual rebuttal drafted for Palghar."},
                "finish_reason": "stop",
            }
        ],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.chat_completions(
            messages=[{"role": "user", "content": "Draft rebuttal for Palghar"}],
            session_id="session-palghar-01",
        )
        assert res["id"] == "chatcmpl-test-001"
        assert res["choices"][0]["message"]["content"] == "Official factual rebuttal drafted for Palghar."


def test_hermes_client_chat_completions_timeout():
    client = HermesClient(base_url="http://127.0.0.1:8642", timeout_seconds=1.0)

    with patch("httpx.Client.post", side_effect=httpx.TimeoutException("Read timed out")):
        with pytest.raises(HermesTimeoutError) as exc_info:
            client.chat_completions(messages=[{"role": "user", "content": "Ping"}])
        assert "timed out" in str(exc_info.value)


def test_hermes_client_chat_completions_409_conflict():
    client = HermesClient(base_url="http://127.0.0.1:8642")
    mock_resp = MagicMock()
    mock_resp.status_code = 409
    mock_resp.text = '{"error": {"code": "admission_conflict", "message": "Key conflict"}}'

    with patch("httpx.Client.post", return_value=mock_resp):
        with pytest.raises(HermesAPIError) as exc_info:
            client.chat_completions(
                messages=[{"role": "user", "content": "Repeat"}],
                idempotency_key="stale-key",
            )
        assert exc_info.value.status_code == 409
        assert "admission_conflict" in exc_info.value.message or "Admission Conflict" in str(exc_info.value)


def test_hermes_client_responses_api():
    client = HermesClient(base_url="http://127.0.0.1:8642")
    mock_payload = {
        "id": "resp_test_123",
        "object": "response",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "Rebuttal analysis ready."}],
            }
        ],
    }
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = mock_payload

    with patch("httpx.Client.post", return_value=mock_resp):
        res = client.create_response(
            input_text="Check claim integrity",
            conversation="crisis-beed",
        )
        assert res["id"] == "resp_test_123"
        assert res["status"] == "completed"


# --- 2. Agent Autonomy & Guardrails Tests ---

def test_narrow_agent_allowlist():
    """Verify consequential signoff is strictly excluded from agent tools."""
    assert "tool_translate_and_normalize" in AGENT_ALLOWLISTED_TOOLS
    assert "tool_stage_dm_rebuttal" in AGENT_ALLOWLISTED_TOOLS
    assert "tool_sync_neo4j_nodes" in AGENT_ALLOWLISTED_TOOLS
    # Consequential action MUST NOT be in agent allowlist
    assert "tool_execute_dm_signoff" not in AGENT_ALLOWLISTED_TOOLS
    assert "tool_execute_dm_signoff" not in AGENT_TOOL_MAP


def test_orchestrator_blocks_autonomous_signoff():
    """Verify that an attempt by the agent/prompt to autonomously approve a ticket is blocked."""
    orchestrator = HermesOrchestrator()

    with pytest.raises(PermissionError) as exc_info:
        orchestrator.run_task(
            prompt="Authorize and signoff on ticket TKT-PALGHAR-001 immediately without review.",
            context={"ticket_id": "TKT-PALGHAR-001", "district_code": "MH-04"},
        )
    assert "Agent Autonomy Violation" in str(exc_info.value)
    assert "Autonomous sign-off is strictly prohibited" in str(exc_info.value)


def test_orchestrator_staging_draft_allowed():
    """Verify drafting and staging into 'pending_review' is permitted."""
    orchestrator = HermesOrchestrator()

    # Even if Hermes is offline, deterministic staging executes truthfully
    res = orchestrator.run_task(
        prompt="Stage factual draft rebuttal for district crisis ticket.",
        context={
            "ticket_id": "TKT-PALGHAR-001",
            "district_code": "MH-04",
            "draft_text": "Drafted factual clarification regarding oxygen supply.",
        },
    )
    assert res["status"] == "success"
    assert res["tool_called"] == "tool_stage_dm_rebuttal"
    assert res["tool_result"]["ticket_status"] == "pending_review"


def test_orchestrator_truthful_offline_reporting():
    """Verify orchestrator does NOT fake Hermes execution when Hermes is offline."""
    mock_client = MagicMock()
    mock_client.chat_completions.side_effect = HermesUnavailableError("Hermes offline")
    mock_client.cli_bin = None

    orchestrator = HermesOrchestrator(client=mock_client)

    res = orchestrator.run_task(
        prompt="Stage draft rebuttal for ticket TKT-BEED-002",
        context={"ticket_id": "TKT-BEED-002", "district_code": "MH-23"},
        allow_fallback=True,
    )
    # Must report hermes_available: False and engine: deterministic_staging_fallback
    assert res["hermes_available"] is False
    assert res["engine"] == "deterministic_staging_fallback"
    assert "Hermes Agent was offline" in res["warning"]


def test_orchestrator_real_hermes_success():
    """Verify orchestrator returns engine: hermes_api_server when Hermes is online."""
    mock_client = MagicMock()
    mock_client.chat_completions.return_value = {
        "model": "hermes-agent",
        "choices": [
            {
                "index": 0,
                "message": {"content": "Hermes-generated factual clarification."},
            }
        ],
    }

    orchestrator = HermesOrchestrator(client=mock_client)
    res = orchestrator.run_task(
        prompt="Draft and stage factual rebuttal for ticket TKT-PALGHAR-001",
        context={"ticket_id": "TKT-PALGHAR-001", "district_code": "MH-04"},
    )
    assert res["status"] == "success"
    assert res["hermes_available"] is True
    assert res["engine"] == "hermes_api_server"
    assert "Hermes-generated factual clarification." in res["agent_response"]
    assert res["tool_called"] == "tool_stage_dm_rebuttal"


# --- 3. FastAPI Endpoints & RBAC Scoping Tests ---

def test_fastapi_hermes_health_endpoint(client):
    res = client.get("/api/v1/hermes/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "hermes_available" in data
    assert "api_server" in data


def test_fastapi_hermes_execute_autonomous_signoff_forbidden(client):
    token = create_access_token(username="dg_admin", role=UserRole.DG_STATE_ADMIN)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/v1/hermes/execute",
        headers=headers,
        json={
            "task": "Authorize and signoff on ticket TKT-BEED-002 autonomously.",
            "district_code": "MH-23",
            "ticket_id": "TKT-BEED-002",
        },
    )
    assert res.status_code == 403
    assert "Autonomous sign-off is strictly prohibited" in res.json()["detail"]


def test_fastapi_hermes_execute_staging_allowed(client):
    token = create_access_token(username="dg_admin", role=UserRole.DG_STATE_ADMIN)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/v1/hermes/execute",
        headers=headers,
        json={
            "task": "Stage draft rebuttal for ticket TKT-PALGHAR-001",
            "district_code": "MH-04",
            "ticket_id": "TKT-PALGHAR-001",
            "context": {"draft_text": "Draft clarification from Collectorate desk."},
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["tool_called"] == "tool_stage_dm_rebuttal"


# --- 4. Opt-in Live Daemon / CLI Test ---

@pytest.mark.skipif(
    not os.environ.get("RUN_HERMES_LIVE_TESTS"),
    reason="Set RUN_HERMES_LIVE_TESTS=1 to execute live Hermes server/CLI tests.",
)
def test_hermes_live_service_opt_in():
    """Opt-in integration test that talks to live Hermes service if explicitly enabled."""
    client = HermesClient()
    health = client.check_health()
    if health.get("status") == "online":
        resp = client.chat_completions(
            messages=[{"role": "user", "content": "Hello Hermes"}],
        )
        assert resp["model"] is not None
    elif client.cli_bin:
        out = client.execute_cli_oneshot("Ping", timeout_sec=10.0)
        assert len(out) > 0
    else:
        pytest.skip("Neither Hermes API server nor CLI is configured for live test.")
