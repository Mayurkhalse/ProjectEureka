"""
Tests for SAVI Platform Fallback & Spoof Data Analysis Engine.
Verifies:
1. Generation of mathematically coherent SAVI framework data analysis on scraping fallback.
2. Open-Jev System 1 primitives (Choice, Noul, Score) presence and valid ranges.
3. Isolation Rainforest anomaly action (PASS_ORGANIC, FLAG_ELEVATED, QUARANTINE).
4. Extracted knowledge triplets and entailment probabilities.
5. Nous Hermes Autonomous ReAct trajectory generation in fallback mode.
6. API endpoint graceful degradation to spoof analysis upon pipeline exceptions.
"""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from savi.api.main import app
from savi.api.spoof_generator import generate_spoof_savi_analysis


@pytest.fixture
def client():
    return TestClient(app)


def test_generate_spoof_savi_analysis_trusted_outlet():
    res = generate_spoof_savi_analysis(
        url="https://www.reuters.com/markets/asia/global-chips-rebound-2026",
        title="Global Semiconductor Manufacturing Output Accelerates",
        raw_text="Semiconductor producers reported record wafer shipments driven by edge AI demand.",
        domain="reuters.com",
        use_hermes=False,
    )

    assert res["status"] == "success"
    assert "analysis_id" in res
    assert res["domain"] == "reuters.com"
    assert res["overall_verdict"] == "VERIFIED_ORGANIC"
    assert res["trust_score"] >= 75.0
    assert res["is_fallback_analysis"] is True

    # SAVI Quad Metrics
    metrics = res["savi_metrics"]
    assert -1.0 <= metrics["sentiment_dynamics"] <= 1.0
    assert 0.0 <= metrics["factual_accuracy"] <= 1.0
    assert 0.0 <= metrics["logical_validation"] <= 1.0
    assert 0.0 <= metrics["news_impact_index"] <= 10.0

    # Open-Jev System 1 Head
    oj = res["open_jev"]
    assert oj["credibility_choice"] == "VERIFIED_CREDIBLE"
    assert 0.0 <= oj["credibility_confidence"] <= 1.0
    assert 0.0 <= oj["manipulation_noul_yes"] <= 0.20
    assert 4.0 <= oj["integrity_score"] <= 5.0

    # Isolation Rainforest Anomaly
    rf = res["anomaly_detection"]
    assert rf["action"] == "PASS_ORGANIC"
    assert 0.0 <= rf["anomaly_score"] <= 0.50

    # Key Claim Triplets
    assert len(res["key_claims"]) >= 2
    for t in res["key_claims"]:
        assert "subject" in t
        assert "predicate" in t
        assert "object" in t
        assert "verdict" in t


def test_generate_spoof_savi_analysis_with_hermes_react():
    res = generate_spoof_savi_analysis(
        url="https://www.bloomberg.com/news/markets/oil-stabilizes",
        title="OPEC+ Maintains Production Guidance Amid Stable Demand",
        domain="bloomberg.com",
        use_hermes=True,
    )

    assert res["hermes_investigation"] is not None
    h = res["hermes_investigation"]
    assert "verdict" in h
    assert "confidence_score" in h
    assert "executive_summary" in h
    assert "trajectory" in h
    steps = h["trajectory"]["steps"]
    assert len(steps) >= 3
    assert steps[0]["step_index"] == 1
    assert "thought" in steps[0]
    assert "observation" in steps[0]


def test_generate_spoof_savi_analysis_sensational_claim():
    res = generate_spoof_savi_analysis(
        url="https://conspiracy-daily.info/shocking-miracle-breakthrough",
        title="SHOCKING BOMBSHELL: Miracle Discovery Exposed in Secret File",
        raw_text="Unbelievable catastrophe revealed after secret leak exposes miracle discovery.",
        domain="conspiracy-daily.info",
        use_hermes=False,
    )

    assert res["trust_score"] < 70.0
    assert res["overall_verdict"] in ("CAUTION_FLAGGED", "HIGH_RISK_ANOMALY")
    assert res["anomaly_detection"]["action"] in ("FLAG_ELEVATED", "QUARANTINE")


def test_api_endpoint_fallback_on_pipeline_exception(client):
    req_payload = {
        "url": "https://www.test-news.org/article",
        "title": "Central Bank Policy Statement",
        "raw_text": "Economic committee confirms monetary target rates.",
        "domain": "test-news.org",
    }

    # Force an exception inside the underlying pipeline to test graceful fallback
    with patch("savi.api.main.orchestrator._execute_analyze_news_article", side_effect=RuntimeError("Simulated Neo4j network timeout")):
        response = client.post("/api/v1/extension/analyze", json=req_payload)
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "success"
        assert "trust_score" in data
        assert "savi_metrics" in data
        assert "open_jev" in data
        assert "anomaly_detection" in data
        assert "key_claims" in data
        assert data.get("is_fallback_analysis") is True
        assert "Simulated Neo4j" in data.get("fallback_engine", "")
