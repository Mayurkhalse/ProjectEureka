"""Benchmark test validating 100-Point Composite Index calculations against official DGIPR answer key.

Verifies:
1. 100% agreement across all 36 Maharashtra districts in expected_scores.csv.
2. Official planted edge cases:
   - Thane rank #1 (96.75 pts)
   - Pune volume saturation (541 releases -> 25.0 pts)
   - Washim zero speed (avg TAT 131.0 min -> 0.0 pts, total score 16.0 pts)
   - Hingoli & Gadchiroli zero rumors (crisis_total == 0 -> strictly 25.0 pts)
   - Nagpur rumor at 90.0 min (strictly < 90.0 required -> counts as breach, 12 of 14 ok)
3. CSVAdapter validation rejecting invalid temporal sequence (published < event).
4. API endpoints for /api/v1/scoring/leaderboard, /api/v1/scoring/district/{id}, and /api/v1/quad/import/csv.
"""

import csv
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from eureka.api.auth import create_access_token
from eureka.api.main import app
from eureka.models.enums import UserRole
from eureka.quad_ingestion.csv_adapter import CSVAdapter
from eureka.scoring.scoring_engine import CompositeScoringEngine


@pytest.fixture
def api_client():
    return TestClient(app)


@pytest.fixture
def dg_admin_token():
    return create_access_token(
        username="dg-admin-bench",
        role=UserRole.DG_STATE_ADMIN,
        district_code="MH-HQ",
    )


def test_all_36_districts_match_expected_scores():
    """Verify that all 36 districts computed match expected_scores.csv within 0.02 tolerance."""
    seed_dir = CompositeScoringEngine.resolve_seed_dir()
    expected_path = seed_dir / "expected_scores.csv"
    assert expected_path.exists(), f"expected_scores.csv not found at {expected_path}"

    with open(expected_path, mode="r", encoding="utf-8-sig") as f:
        expected_rows = list(csv.DictReader(f))

    assert len(expected_rows) == 36, f"Expected 36 districts, found {len(expected_rows)}"

    computed_districts = CompositeScoringEngine.compute_district_scores_from_csv(seed_dir=str(seed_dir))
    assert len(computed_districts) == 36

    computed_by_id = {d["district_id"]: d for d in computed_districts}

    for exp in expected_rows:
        did = int(exp["district_id"])
        comp = computed_by_id.get(did)
        assert comp is not None, f"Missing district {did} in computed scores"

        name = exp["district"]
        # Basic counts
        assert comp["releases"] == int(exp["releases"]), f"{name}: releases mismatch"
        assert abs(comp["avg_tat_min"] - float(exp["avg_tat_min"])) <= 0.15, f"{name}: avg_tat mismatch"
        assert abs(comp["net_sentiment"] - float(exp["net_sentiment"])) <= 0.02, f"{name}: net_sentiment mismatch"
        assert comp["crisis_ok"] == int(exp["crisis_ok"]), f"{name}: crisis_ok mismatch"
        assert comp["crisis_total"] == int(exp["crisis_total"]), f"{name}: crisis_total mismatch"

        # Four Pillars (within 0.02 pts)
        assert abs(comp["volume_pts"] - float(exp["volume_pts"])) <= 0.02, f"{name}: volume_pts mismatch"
        assert abs(comp["speed_pts"] - float(exp["speed_pts"])) <= 0.02, f"{name}: speed_pts mismatch"
        assert abs(comp["sentiment_pts"] - float(exp["sentiment_pts"])) <= 0.02, f"{name}: sentiment_pts mismatch"
        assert abs(comp["crisis_pts"] - float(exp["crisis_pts"])) <= 0.02, f"{name}: crisis_pts mismatch"

        # Total Composite Score (within 0.02 pts)
        assert abs(comp["total_score"] - float(exp["total_score"])) <= 0.02, f"{name}: total_score mismatch"

        # Auxiliary Metrics
        assert abs(comp["output_velocity_pct"] - float(exp["output_velocity_pct"])) <= 0.15, f"{name}: velocity mismatch"
        assert abs(comp["positive_share_pct"] - float(exp["positive_share_pct"])) <= 0.15, f"{name}: positive_share mismatch"
        assert abs(comp["top5_share_pct"] - float(exp["top5_share_pct"])) <= 0.15, f"{name}: top5_share mismatch"


def test_edge_cases_planted_in_benchmark_data():
    """Verify specific planted edge cases across benchmark districts."""
    seed_dir = CompositeScoringEngine.resolve_seed_dir()
    scores = CompositeScoringEngine.compute_district_scores_from_csv(seed_dir=str(seed_dir))
    scores_by_id = {d["district_id"]: d for d in scores}

    # 1. Rank 1 is Thane with 96.75
    assert scores[0]["district"] == "Thane"
    assert scores[0]["district_id"] == 3
    assert scores[0]["total_score"] == 96.75
    assert scores[0]["rank"] == 1

    # 2. Pune volume saturation at 25.0 points with 541 releases
    pune = scores_by_id[8]
    assert pune["releases"] == 541
    assert pune["volume_pts"] == 25.0

    # 3. Washim speed is 0.0 with 131.0 min TAT, rank 36 with 16.0 total
    washim = scores_by_id[28]
    assert washim["avg_tat_min"] == 131.0
    assert washim["speed_pts"] == 0.0
    assert washim["total_score"] == 16.0
    assert washim["rank"] == 36

    # 4. Hingoli (district 25) & Gadchiroli (district 36): 0 rumors -> 25.0 points
    hingoli = scores_by_id[25]
    assert hingoli["crisis_total"] == 0
    assert hingoli["crisis_pts"] == 25.0

    gadchiroli = scores_by_id[36]
    assert gadchiroli["crisis_total"] == 0
    assert gadchiroli["crisis_pts"] == 25.0

    # 5. Nagpur (district 31): rumor resolved at exactly 90.0m is a breach!
    nagpur = scores_by_id[31]
    assert nagpur["crisis_total"] == 14
    assert nagpur["crisis_ok"] == 12  # exactly 90.0m is breached, so 12 of 14 ok
    assert nagpur["crisis_pts"] == 21.43


def test_csv_adapter_temporal_sequence_rejection():
    """Verify that CSVAdapter correctly rejects invalid_press_releases.csv records where published < event."""
    adapter = CSVAdapter()
    invalid_csv_path = adapter.resolve_file_path("invalid_press_releases.csv")
    assert invalid_csv_path.exists()

    with open(invalid_csv_path, mode="r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))

    assert len(reader) == 3
    for row in reader:
        is_valid, reason = adapter.validate_press_release(row)
        assert not is_valid
        assert "Invalid temporal sequence" in reason or "before event" in reason


def test_scoring_api_leaderboard_endpoint(api_client, dg_admin_token):
    """Test GET /api/v1/scoring/leaderboard returns all 36 ranked districts."""
    headers = {"Authorization": f"Bearer {dg_admin_token}"}
    response = api_client.get("/api/v1/scoring/leaderboard", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "success"
    assert data["total_districts"] == 36
    leaderboard = data["leaderboard"]
    assert len(leaderboard) == 36

    # Verify rank 1 is Thane
    top1 = leaderboard[0]
    assert top1["rank"] == 1
    assert top1["district"] == "Thane"
    assert top1["total_score"] == 96.75


def test_scoring_api_single_district_endpoint(api_client, dg_admin_token):
    """Test GET /api/v1/scoring/district/{id} returns district details."""
    headers = {"Authorization": f"Bearer {dg_admin_token}"}
    # Test district 3 (Thane)
    response = api_client.get("/api/v1/scoring/district/3", headers=headers)
    assert response.status_code == 200

    thane = response.json()
    assert thane["district"] == "Thane"
    assert thane["volume_pts"] == 25.0
    assert thane["speed_pts"] == 25.0
    assert thane["crisis_pts"] == 25.0
    assert thane["total_score"] == 96.75

    # Test nonexistent district returns 404
    non_existent = api_client.get("/api/v1/scoring/district/999", headers=headers)
    assert non_existent.status_code == 404


def test_quad_import_csv_endpoint(api_client, dg_admin_token):
    """Test POST /api/v1/quad/import/csv dispatches Celery task."""
    headers = {"Authorization": f"Bearer {dg_admin_token}"}
    payload = {
        "csv_file": "press_releases.csv",
        "lane": "LANE_1_API_GOV",
    }
    with patch("eureka.api.routers.quad.ingest_csv_task.delay") as mock_delay:
        mock_task = MagicMock()
        mock_task.id = "mock-celery-task-id-1234"
        mock_delay.return_value = mock_task

        response = api_client.post("/api/v1/quad/import/csv", json=payload, headers=headers)
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "dispatched"
        assert data["task_id"] == "mock-celery-task-id-1234"
        assert data["csv_file"] == "press_releases.csv"
        assert data["adapter"] == "CSVAdapter"
        mock_delay.assert_called_once_with(csv_filename="press_releases.csv", lane="LANE_1_API_GOV")
