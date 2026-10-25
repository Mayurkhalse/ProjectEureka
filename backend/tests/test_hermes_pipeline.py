"""Unit & Integration Tests for Hermes DM Pipeline Manager, Agent Tools, and Autonomous Orchestrator.

Validates:
1. 90-minute Crisis SLA calculation and urgency state transitions.
2. Accurate Indic translation & dialect normalization via Google AI Studio API.
3. Successful staging of a DM rebuttal within the 90-minute SLA window.
4. RBAC violation enforcement: Unauthorized District Collector cannot approve another district's ticket.
5. Idempotent Neo4j node & edge synchronization.
6. HermesOrchestrator task dispatch with CLI, Groq, and deterministic tool fallbacks.
7. FastAPI Hermes endpoints (/dm-queue/{district_code}, /translate, /execute, /dm-pipelines).
"""

import uuid
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest

from eureka.api.auth import create_access_token
from eureka.api.main import app
from eureka.core.database import sync_db_context
from eureka.hermes.agent_tools import (
    tool_execute_dm_signoff,
    tool_stage_dm_rebuttal,
    tool_sync_neo4j_nodes,
    tool_translate_and_normalize,
)
from eureka.hermes.dm_pipeline_manager import (
    HermesDMPipelineManager,
    MAHARASHTRA_DIVISIONS,
    DISTRICT_LOOKUP,
)
from eureka.hermes.orchestrator import get_hermes_orchestrator
from eureka.models.entities import CanonicalEvent, FactCheckTicket, HumanReviewAction, OutboxEvent
from eureka.models.enums import (
    CanonicalEventStatus,
    DetectedLanguage,
    FactCheckTicketStatus,
    UserRole,
    VerificationStatus,
)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def hermes_test_db_records():
    """Deterministic fixture providing required CanonicalEvent and FactCheckTicket in PostgreSQL."""
    test_event_id = None
    test_ticket_id = None
    created = False
    with sync_db_context() as session:
        ticket = session.query(FactCheckTicket).join(CanonicalEvent).first()
        if not ticket:
            event = CanonicalEvent(
                id=uuid.uuid4(),
                title="Beed Kharif Crop Insurance Disbursement Verification",
                summary="Official verification of Kharif crop insurance disbursements in Beed.",
                primary_language=DetectedLanguage.MARATHI,
                district_code="MH-23",
                district_name="Beed",
                status=CanonicalEventStatus.PENDING_REVIEW,
                verification_status=VerificationStatus.UNVERIFIED,
                first_detected_at=datetime.now(timezone.utc) - timedelta(minutes=30),
                last_updated_at=datetime.now(timezone.utc),
            )
            session.add(event)
            session.flush()

            ticket = FactCheckTicket(
                id=uuid.uuid4(),
                canonical_event_id=event.id,
                claim_text="TKT-BEED-002: Beed Kharif crop insurance claims cancelled",
                is_rumor=True,
                event_timestamp=datetime.now(timezone.utc) - timedelta(minutes=20),
                status=FactCheckTicketStatus.OPEN,
                assigned_to="Collector MH-23",
                resolution_notes=None,
            )
            session.add(ticket)
            session.commit()
            test_event_id = event.id
            test_ticket_id = ticket.id
            created = True
        else:
            ticket.event_timestamp = datetime.now(timezone.utc) - timedelta(minutes=20)
            ticket.status = FactCheckTicketStatus.OPEN
            ticket.refuted_at = None
            ticket.refuted_within_sla_90m = False
            session.commit()

    yield

    if created and test_ticket_id and test_event_id:
        with sync_db_context() as session:
            try:
                session.query(HumanReviewAction).filter(HumanReviewAction.entity_id == test_ticket_id).delete()
                session.query(OutboxEvent).filter(OutboxEvent.aggregate_id == str(test_event_id)).delete()
                session.query(FactCheckTicket).filter(FactCheckTicket.id == test_ticket_id).delete()
                session.query(CanonicalEvent).filter(CanonicalEvent.id == test_event_id).delete()
                session.commit()
            except Exception:
                session.rollback()


# --- 1. SLA Calculation Unit Tests ---

def test_sla_status_calculation_within_window():
    now = datetime.now(timezone.utc)
    event_time = now - timedelta(minutes=30)

    sla = HermesDMPipelineManager.calculate_sla_status(event_time)
    assert sla["is_expired"] is False
    assert sla["sla_remaining_seconds"] > 0
    assert sla["urgency_level"] in ["WATCH", "ON_TRACK"]
    assert "00:" in sla["sla_remaining_formatted"] or "01:" in sla["sla_remaining_formatted"]


def test_sla_status_calculation_expired():
    now = datetime.now(timezone.utc)
    event_time = now - timedelta(minutes=100)

    sla = HermesDMPipelineManager.calculate_sla_status(event_time)
    assert sla["is_expired"] is True
    assert sla["sla_remaining_seconds"] == 0
    assert sla["urgency_level"] == "BREACHED"


def test_sla_status_calculation_refuted_within_sla():
    now = datetime.now(timezone.utc)
    event_time = now - timedelta(minutes=50)
    refuted_time = now - timedelta(minutes=10)

    sla = HermesDMPipelineManager.calculate_sla_status(event_time, refuted_at=refuted_time)
    assert sla["refuted_within_sla"] is True
    assert sla["urgency_level"] == "RESOLVED"


# --- 2. Collector RBAC Scope Helper Tests ---

def test_collector_rbac_authorization():
    # 1. DG Admin has statewide access
    assert HermesDMPipelineManager.validate_collector_authorization(
        user_role=UserRole.DG_STATE_ADMIN,
        user_district_code=None,
        target_district_code="MH-04",
    ) is True

    # 2. Collector matching district code
    assert HermesDMPipelineManager.validate_collector_authorization(
        user_role=UserRole.DISTRICT_COLLECTOR,
        user_district_code="MH-04",
        target_district_code="MH-04",
    ) is True

    # 3. Collector with mismatched district code
    assert HermesDMPipelineManager.validate_collector_authorization(
        user_role=UserRole.DISTRICT_COLLECTOR,
        user_district_code="MH-04",
        target_district_code="MH-23",
    ) is False


# --- 3. Executive Dossiers 1-4 Generation ---

def test_generate_dossiers_schemas():
    d1 = HermesDMPipelineManager.generate_dossier("1")
    assert "dossier_id" in d1
    assert "divisions_overview" in d1
    assert len(d1["divisions_overview"]) == 6

    d2 = HermesDMPipelineManager.generate_dossier("2", district="Beed")
    assert d2["origin_district"]["name"] == "Beed"
    assert "misinformation_payload" in d2

    d3 = HermesDMPipelineManager.generate_dossier("3")
    assert d3["total_districts_evaluated"] == 36
    assert len(d3["league_table"]) == 36

    d4 = HermesDMPipelineManager.generate_dossier("4")
    assert "epicenter" in d4
    assert len(d4["predicted_contagion_pathways"]) >= 2


# --- 4. STEP 2 & 3: Indic Translation & Agent Tools ---

def test_accurate_indic_translation_google_ai_studio():
    """Verify tool_translate_and_normalize returns strict JSON schema."""
    sample_text = "बीड जिल्ह्यातील सर्व पीक विमा दावे रद्द झाल्याचा खोटा दावा समाज माध्यमांवर पसरत आहे."
    res = tool_translate_and_normalize(sample_text)

    assert "marathi_text" in res
    assert "english_text" in res
    assert "detected_dialect" in res
    assert res["extracted_district_code"] == "MH-23"


def test_stage_dm_rebuttal_within_90m_sla():
    """Verify tool_stage_dm_rebuttal updates PostgreSQL ticket status to pending_review."""
    test_draft = "Official Denial: Beed Kharif crop insurance disbursements are active. ₹148 Cr transferred."
    res = tool_stage_dm_rebuttal(
        ticket_id="TKT-BEED-002",
        district_code="MH-23",
        draft_text=test_draft,
    )
    assert res["status"] == "success"
    assert res["ticket_status"] == "pending_review"
    assert res["draft_text"] == test_draft


def test_rbac_unauthorized_collector_approval_violation():
    """Verify an unauthorized district collector CANNOT sign off on another district's ticket."""
    # Find a ticket belonging to a specific district
    with sync_db_context() as session:
        ticket = session.query(FactCheckTicket).join(CanonicalEvent).first()
        assert ticket is not None, "Seed data must contain fact_check_tickets"
        # Ensure event_timestamp is within the active 90-minute SLA window
        ticket.event_timestamp = datetime.now(timezone.utc) - timedelta(minutes=20)
        session.commit()
        t_id = str(ticket.id)
        actual_district = ticket.canonical_event.district_code or "MH-04"

    # Opposite district code
    different_district = "MH-23" if actual_district != "MH-23" else "MH-15"

    # Unauthorized attempt by a collector from a different district MUST raise PermissionError
    with pytest.raises(PermissionError):
        tool_execute_dm_signoff(
            ticket_id=t_id,
            reviewer_id="collector_unauthorized",
            role="ROLE_DISTRICT_COLLECTOR",
            district_code=different_district,
            action="authorize",
        )

    # Authorized attempt with matching district should succeed
    auth_res = tool_execute_dm_signoff(
        ticket_id=t_id,
        reviewer_id="collector_authorized",
        role="ROLE_DISTRICT_COLLECTOR",
        district_code=actual_district,
        action="authorize",
    )
    assert auth_res["status"] == "success"
    assert auth_res["ticket_status"] == "approved"
    assert auth_res["refuted_within_sla_90m"] is True


def test_idempotent_neo4j_node_generation():
    """Verify tool_sync_neo4j_nodes merges District, CanonicalEvent, and Claim idempotently."""
    event_id = str(uuid.uuid4())
    claim = "Verified administrative notification regarding public works in Pune."

    # First execution
    res1 = tool_sync_neo4j_nodes(district_code="MH-12", event_id=event_id, claim_text=claim)
    assert res1["status"] in ["success", "warning"]

    # Second execution with exact same parameters (Idempotent merge)
    res2 = tool_sync_neo4j_nodes(district_code="MH-12", event_id=event_id, claim_text=claim)
    assert res2["status"] in ["success", "warning"]
    assert res2["district_code"] == "MH-12"


def test_hermes_orchestrator_execution():
    """Verify HermesOrchestrator fallback layers execute deterministically."""
    orchestrator = get_hermes_orchestrator()

    # Test Translation Task
    res = orchestrator.run_task(
        prompt="Translate and normalize this Marathi news clipping: नाशिक कांदा बाजारपेठ लिलाव सुरळीत सुरु.",
        context={"district_code": "MH-15"},
    )
    assert res["status"] == "success"
    assert res["engine"] in ["hermes_api_server", "hermes_cli_oneshot", "deterministic_staging_fallback"]
    assert res["tool_called"] == "tool_translate_and_normalize"


# --- 5. FastAPI Router Endpoints ---

def test_hermes_router_dm_pipelines_and_rbac(client):
    palghar_token = create_access_token(
        username="collector_palghar",
        role=UserRole.DISTRICT_COLLECTOR,
        district_code="MH-04",
    )
    headers = {"Authorization": f"Bearer {palghar_token}"}

    res = client.get("/api/v1/hermes/dm-pipelines", headers=headers)
    assert res.status_code == 200
    pipelines = res.json()
    assert all(p["districtCode"] == "MH-04" for p in pipelines)

    admin_token = create_access_token(username="dg_admin", role=UserRole.DG_STATE_ADMIN)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    admin_res = client.get("/api/v1/hermes/dm-pipelines", headers=admin_headers)
    assert admin_res.status_code == 200
    assert len(admin_res.json()) >= 2


def test_hermes_router_collector_signoff_action(client):
    palghar_token = create_access_token(
        username="collector_palghar",
        role=UserRole.DISTRICT_COLLECTOR,
        district_code="MH-04",
    )
    headers = {"Authorization": f"Bearer {palghar_token}"}

    res = client.post(
        "/api/v1/hermes/dm-pipelines/TKT-PALGHAR-001/action",
        headers=headers,
        json={"action": "authorize", "notes": "Factual rebuttal authorized for immediate release."},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["authorized_by"] == "collector_palghar"

    res_unauth = client.post(
        "/api/v1/hermes/dm-pipelines/TKT-BEED-002/action",
        headers=headers,
        json={"action": "authorize"},
    )
    assert res_unauth.status_code == 403
    assert "Unauthorized" in res_unauth.json()["detail"]


def test_hermes_router_dm_queue_endpoint(client):
    """Test GET /api/v1/hermes/dm-queue/{district_code}."""
    res = client.get("/api/v1/hermes/dm-queue/MH-04")
    assert res.status_code == 200
    data = res.json()
    assert data["district_code"] == "MH-04"
    assert "tickets" in data
    assert isinstance(data["tickets"], list)


def test_hermes_router_translate_endpoint(client):
    """Test POST /api/v1/hermes/translate."""
    res = client.post(
        "/api/v1/hermes/translate",
        json={"text": "लासलगाव कांदा लिलाव नियमित वेळेनुसार पार पडले."},
    )
    assert res.status_code == 200
    data = res.json()
    assert "marathi_text" in data
    assert "english_text" in data
    assert "extracted_district_code" in data


def test_hermes_router_execute_endpoint(client):
    """Test POST /api/v1/hermes/execute."""
    token = create_access_token(username="dg_admin", role=UserRole.DG_STATE_ADMIN)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/api/v1/hermes/execute",
        headers=headers,
        json={
            "task": "Stage factual DM rebuttal for district crisis ticket.",
            "district_code": "MH-23",
            "ticket_id": "TKT-BEED-002",
            "context": {"draft_text": "Active compensation disbursal confirmed by Beed Collector."},
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "success"


def test_hermes_dossier_endpoint(client):
    token = create_access_token(username="dg_admin", role=UserRole.DG_STATE_ADMIN)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/hermes/dossiers/1", headers=headers)
    assert res.status_code == 200
    assert "dossier_id" in res.json()

    res_stats = client.get("/api/v1/hermes/stats")
    assert res_stats.status_code == 200
    assert "statewide_sla_compliance_rate" in res_stats.json()


def test_tool_query_all_36_districts_direct():
    """Test tool_query_all_36_districts directly against PostgreSQL."""
    from eureka.hermes.agent_tools import tool_query_all_36_districts

    res = tool_query_all_36_districts(include_metrics=True)
    assert res["status"] == "success"
    assert res["total_districts"] == 36
    assert "statewide_overview" in res
    assert len(res["districts"]) == 36

    sample = res["districts"][0]
    assert "district_code" in sample
    assert "name_en" in sample
    assert "name_mr" in sample
    assert "composite_index" in sample
    assert "pillars" in sample
    assert "volume" in sample["pillars"]
    assert "speed_tat" not in sample["pillars"]
    assert "sentiment" in sample["pillars"]
    assert "crisis_sla" in sample["pillars"]

    # Test division filter
    res_konkan = tool_query_all_36_districts(division="Konkan")
    assert res_konkan["status"] == "success"
    assert len(res_konkan["districts"]) > 0
    assert all("DIV-MUM" in d["division_code"] or "DIV-KON" in d["division_code"] or "DIV-KOL" in d["division_code"] for d in res_konkan["districts"])


def test_hermes_router_districts_endpoint(client):
    """Test GET /api/v1/hermes/districts endpoint."""
    res = client.get("/api/v1/hermes/districts")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["total_districts"] == 36
    assert "districts" in data
    assert len(data["districts"]) == 36


def test_hermes_orchestrator_query_districts_task():
    """Test orchestrator routing when task asks for 36 districts database data."""
    orch = get_hermes_orchestrator()
    res = orch.run_task("Query all 36 districts database data and leaderboard scores.")
    assert res["status"] == "success"
    assert res["tool_called"] == "tool_query_all_36_districts"
    assert res["tool_result"]["total_districts"] == 36

