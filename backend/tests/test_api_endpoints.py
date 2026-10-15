"""Integration tests for FastAPI endpoints, RBAC, and review state machine in Project EUREKA."""

import os
import pytest
from fastapi.testclient import TestClient

from eureka.api.main import app
from eureka.api.auth import create_access_token
from eureka.models.enums import UserRole


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["engine"] == "Project EUREKA (DGIPR Maha-Command Center)"


def test_ipcs_endpoint_returns_not_configured(client):
    # Obtain token for DG State Admin
    token = create_access_token(username="admin_test", role=UserRole.DG_STATE_ADMIN)
    response = client.get(
        "/api/v1/ipcs/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    # Must strictly return status: not_configured per DGIPR specification
    assert response.json() == {"status": "not_configured"}


def test_auth_token_generation_and_rbac(client):
    # 1. Generate dev token for DIO Desk
    resp = client.post(
        "/api/v1/auth/token",
        json={"username": "dio_user", "role": "DIO Desk", "district_code": "MH-12"},
    )
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    assert token is not None

    # 2. DIO Desk accesses IPCS (allowed for DG_STATE_ADMIN, DIO_DESK)
    allowed_resp = client.get(
        "/api/v1/ipcs/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert allowed_resp.status_code == 200

    # 3. Unauthenticated access rejected with 403/401
    unauth_resp = client.get("/api/v1/ipcs/status")
    assert unauth_resp.status_code in (401, 403)


def test_stgnn_data_preparation_query_structure():
    """Verify StGNNDataPreparation queries Neo4j with correct relationship types."""
    from eureka.processor.stgnn_prep import StGNNDataPreparation

    class MockDriverService:
        def __init__(self):
            self.queries = []

        def run_query(self, query: str, parameters=None):
            self.queries.append((query.strip(), parameters or {}))
            if "District" in query and "AFFECTS" in query and "d2:District" not in query:
                return [{"code": "MH-12", "name": "Pune", "event_count": 5}]
            if "Department" in query:
                return [{"code": "HEALTH", "name": "Public Health", "event_count": 3}]
            if "d1:District" in query and "d2:District" in query:
                return [{"source_district": "MH-12", "target_district": "MH-20", "weight": 2}]
            return []

    mock_driver = MockDriverService()
    graph_data = StGNNDataPreparation.extract_time_window_graph(window_hours=12, driver_service=mock_driver)

    assert graph_data["window_hours"] == 12
    assert "cutoff_timestamp" in graph_data
    assert len(graph_data["nodes"]["districts"]) == 1
    assert len(graph_data["nodes"]["departments"]) == 1
    assert len(graph_data["edges"]) == 1
    assert graph_data["features_summary"]["total_districts"] == 1
    assert graph_data["features_summary"]["total_departments"] == 1
    assert graph_data["features_summary"]["total_spatio_temporal_edges"] == 1

    # Verify edge types queried in Cypher
    district_q = mock_driver.queries[0][0]
    dept_q = mock_driver.queries[1][0]
    edge_q = mock_driver.queries[2][0]

    assert "-[:AFFECTS]->(d)" in district_q
    assert "-[:RELATES_TO]->(dep)" in dept_q
    assert "(d1:District)<-[:AFFECTS]-(e:CanonicalEvent)-[:AFFECTS]->(d2:District)" in edge_q


def test_spatio_temporal_graph_endpoint_rbac(client, monkeypatch):
    """Verify RBAC and response format for /api/v1/graph/spatio-temporal."""
    from eureka.processor.stgnn_prep import StGNNDataPreparation

    # Monkeypatch extract_time_window_graph to avoid external network/db calls in API test
    monkeypatch.setattr(
        StGNNDataPreparation,
        "extract_time_window_graph",
        lambda window_hours=24: {
            "window_hours": window_hours,
            "cutoff_timestamp": "2026-10-14T00:00:00+00:00",
            "nodes": {"districts": [], "departments": []},
            "edges": [],
            "features_summary": {
                "total_districts": 0,
                "total_departments": 0,
                "total_spatio_temporal_edges": 0,
            },
        },
    )

    # 1. DG_STATE_ADMIN has access
    admin_token = create_access_token(username="state_dg", role=UserRole.DG_STATE_ADMIN)
    resp = client.get(
        "/api/v1/graph/spatio-temporal?window_hours=48",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["window_hours"] == 48

    # 2. DISTRICT_COLLECTOR has access
    collector_token = create_access_token(
        username="collector_pune", role=UserRole.DISTRICT_COLLECTOR, district_code="MH-12"
    )
    collector_resp = client.get(
        "/api/v1/graph/spatio-temporal",
        headers={"Authorization": f"Bearer {collector_token}"},
    )
    assert collector_resp.status_code == 200

    # 3. Unauthenticated access rejected
    unauth = client.get("/api/v1/graph/spatio-temporal")
    assert unauth.status_code in (401, 403)


def test_district_performance_report_endpoint(client):
    from eureka.processor.generate_english_synthetic import generate_english_dataset
    from eureka.api.reports_router import _resolve_dataset_path

    path = _resolve_dataset_path()
    if not os.path.exists(path):
        generate_english_dataset(output_path=path, total_rows=1000, chunk_size=1000)

    response = client.get("/api/v1/reports/district-performance")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "evaluated_rows" in data
    assert "leaderboard" in data
    assert len(data["leaderboard"]) > 0

    first_entry = data["leaderboard"][0]
    assert "district" in first_entry
    assert "raw_metrics" in first_entry
    assert "pillar_scores" in first_entry
    assert "total_index" in first_entry


