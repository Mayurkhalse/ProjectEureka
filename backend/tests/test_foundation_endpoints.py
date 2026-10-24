"""Unit tests for Meeting Changes data foundation endpoints (Items 4, 5, 12)."""

import pytest
from fastapi.testclient import TestClient

from eureka.api.auth import create_access_token
from eureka.api.main import app
from eureka.models.enums import UserRole


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def admin_token():
    return create_access_token(
        username="admin_state",
        role=UserRole.DG_STATE_ADMIN,
    )


@pytest.fixture
def thane_collector_token():
    return create_access_token(
        username="collector_thane",
        role=UserRole.DISTRICT_COLLECTOR,
        district_code="MH-04",
    )


@pytest.fixture
def pune_collector_token():
    return create_access_token(
        username="collector_pune",
        role=UserRole.DISTRICT_COLLECTOR,
        district_code="MH-07",
    )


def test_get_ticker_items(client):
    """Verify live news ticker items endpoint returns 12+ items with provenance."""
    res = client.get("/api/v1/ticker")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["provenance"] == "synthetic"
    assert len(data["items"]) >= 12
    first = data["items"][0]
    assert "kind" in first
    assert "text_en" in first
    assert "text_mr" in first


def test_get_district_positions_as_admin(client, admin_token):
    """State admin can view all 10 positions for Thane (MH-04)."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res = client.get("/api/v1/districts/MH-04/positions", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["district_code"] == "MH-04"
    assert data["total_positions"] == 10
    categories = [p["category"] for p in data["positions"]]
    assert "MINISTER" in categories
    assert "MP" in categories
    assert "MLA" in categories
    assert "COLLECTOR" in categories
    assert "SP" in categories
    assert "DIO" in categories
    assert all(p["provenance"] == "synthetic" for p in data["positions"])


def test_get_district_positions_collector_rbac_authorized(client, thane_collector_token):
    """Thane collector can access Thane positions."""
    headers = {"Authorization": f"Bearer {thane_collector_token}"}
    res = client.get("/api/v1/districts/MH-04/positions", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["district_code"] == "MH-04"


def test_get_district_positions_collector_rbac_forbidden(client, pune_collector_token):
    """Pune collector accessing Thane positions must receive 403 Forbidden."""
    headers = {"Authorization": f"Bearer {pune_collector_token}"}
    res = client.get("/api/v1/districts/MH-04/positions", headers=headers)
    assert res.status_code == 403
    assert "RBAC Scope Violation" in res.json()["detail"]


def test_get_hoardings_statewide_and_district(client, admin_token):
    """Verify statewide and district hoardings."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    res_all = client.get("/api/v1/hoardings", headers=headers)
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["total_hoardings"] >= 108

    res_thane = client.get("/api/v1/districts/MH-04/hoardings", headers=headers)
    assert res_thane.status_code == 200
    data_thane = res_thane.json()
    assert data_thane["total_hoardings"] == 3
    h = data_thane["hoardings"][0]
    assert "scheme_name_en" in h
    assert "lat" in h
    assert "lon" in h


def test_get_district_media_monitoring(client, admin_token):
    """Verify clippings, social posts, and TV clips."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Clippings
    res_clip = client.get("/api/v1/districts/MH-04/clippings", headers=headers)
    assert res_clip.status_code == 200
    data_clip = res_clip.json()
    assert data_clip["total_clippings"] == 4
    clip_id = data_clip["clippings"][0]["id"]

    # Social
    res_soc = client.get("/api/v1/districts/MH-04/social", headers=headers)
    assert res_soc.status_code == 200
    data_soc = res_soc.json()
    assert data_soc["total_social_posts"] == 4

    # TV
    res_tv = client.get("/api/v1/districts/MH-04/tv", headers=headers)
    assert res_tv.status_code == 200
    data_tv = res_tv.json()
    assert data_tv["total_tv_clips"] == 2

    # In-App Source Detail
    res_source = client.get(f"/api/v1/sources/clipping/{clip_id}")
    assert res_source.status_code == 200
    source_data = res_source.json()
    assert source_data["id"] == clip_id
    assert source_data["type"] == "clipping"
    assert "source_url" in source_data
