"""Unit & integration tests for Hermes DM Pipeline Manager and Executive Dossiers."""

from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import pytest

from eureka.api.auth import create_access_token
from eureka.api.main import app
from eureka.hermes.dm_pipeline_manager import (
    HermesDMPipelineManager,
    MAHARASHTRA_DIVISIONS,
    DISTRICT_LOOKUP,
)
from eureka.models.enums import UserRole


@pytest.fixture
def client():
    return TestClient(app)


def test_sla_status_calculation_within_window():
    now = datetime.now(timezone.utc)
    event_time = now - timedelta(minutes=30)

    sla = HermesDMPipelineManager.calculate_sla_status(event_time)
    assert sla["is_expired"] is False
    assert sla["sla_remaining_seconds"] > 0
    # ~60 minutes remaining -> WATCH urgency
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


def test_generate_dossiers_schemas():
    # Dossier 1: Morning Bulletin
    d1 = HermesDMPipelineManager.generate_dossier("1")
    assert "dossier_id" in d1
    assert "divisions_overview" in d1
    assert len(d1["divisions_overview"]) == 6
    assert "emergent_early_warnings" in d1

    # Dossier 2: Crisis Alert
    d2 = HermesDMPipelineManager.generate_dossier("2", district="Beed")
    assert d2["origin_district"]["name"] == "Beed"
    assert "misinformation_payload" in d2
    assert "graph_diffusion_vector" in d2

    # Dossier 3: Weekly Rankings (All 36 Districts)
    d3 = HermesDMPipelineManager.generate_dossier("3")
    assert d3["total_districts_evaluated"] == 36
    assert len(d3["league_table"]) == 36
    assert d3["league_table"][0]["rank"] == 1
    assert "pillars" in d3["league_table"][0]

    # Dossier 4: 6-Hour Diffusion Warning
    d4 = HermesDMPipelineManager.generate_dossier("4")
    assert "epicenter" in d4
    assert len(d4["predicted_contagion_pathways"]) >= 2


def test_hermes_router_dm_pipelines_and_rbac(client):
    # Token for Palghar Collector (MH-04)
    palghar_token = create_access_token(
        username="collector_palghar",
        role=UserRole.DISTRICT_COLLECTOR,
        district_code="MH-04",
    )
    headers = {"Authorization": f"Bearer {palghar_token}"}

    # Palghar Collector should see Palghar pipelines
    res = client.get("/api/v1/hermes/dm-pipelines", headers=headers)
    assert res.status_code == 200
    pipelines = res.json()
    assert all(p["districtCode"] == "MH-04" for p in pipelines)

    # State Admin token sees all pipelines
    admin_token = create_access_token(
        username="dg_admin",
        role=UserRole.DG_STATE_ADMIN,
    )
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

    # Authorize Palghar ticket
    res = client.post(
        "/api/v1/hermes/dm-pipelines/TKT-PALGHAR-001/action",
        headers=headers,
        json={"action": "authorize", "notes": "Factual rebuttal authorized for immediate release."},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["authorized_by"] == "collector_palghar"

    # Palghar Collector trying to sign off Beed ticket (MH-23) should get 403 Forbidden
    res_unauth = client.post(
        "/api/v1/hermes/dm-pipelines/TKT-BEED-002/action",
        headers=headers,
        json={"action": "authorize"},
    )
    assert res_unauth.status_code == 403
    assert "Unauthorized" in res_unauth.json()["detail"]


def test_hermes_dossier_endpoint(client):
    token = create_access_token(username="dg_admin", role=UserRole.DG_STATE_ADMIN)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.get("/api/v1/hermes/dossiers/1", headers=headers)
    assert res.status_code == 200
    assert "dossier_id" in res.json()

    res_stats = client.get("/api/v1/hermes/stats")
    assert res_stats.status_code == 200
    assert "statewide_sla_compliance_rate" in res_stats.json()
