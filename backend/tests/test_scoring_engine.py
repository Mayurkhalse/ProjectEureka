"""Unit tests for 100-Point Composite Index Scoring Engine in Project EUREKA.

TAT removed per meeting changes. Weights: Volume 35, Sentiment 35, Crisis SLA 30 (sum = 100).
"""

import pytest
from eureka.core.reference_data import SCORING_CONFIG_V1
from eureka.scoring.scoring_engine import CompositeScoringEngine


def test_scoring_weights_sum_to_100_no_tat():
    """Verify that scoring weights sum strictly to 100 and no TAT pillar remains."""
    weights = SCORING_CONFIG_V1["weights"]
    assert sum(weights.values()) == 100
    assert "tat" not in weights
    assert "speed" not in weights
    assert "speed_tat" not in weights
    assert set(weights.keys()) == {"volume", "sentiment", "crisis_sla"}
    assert weights["volume"] == 35
    assert weights["sentiment"] == 35
    assert weights["crisis_sla"] == 30


def test_volume_pillar_saturation():
    # 0 releases -> 0 points
    assert CompositeScoringEngine.calculate_volume(0) == 0.0

    # 150 releases -> 17.5 points
    assert CompositeScoringEngine.calculate_volume(150) == 17.5

    # 300 releases -> 35 points
    assert CompositeScoringEngine.calculate_volume(300) == 35.0

    # 500 releases -> capped at 35 points
    assert CompositeScoringEngine.calculate_volume(500) == 35.0


def test_sentiment_pillar_nsi_mapping():
    # All positive: NSI = 1.0 -> 35 points
    score_pos, nsi_pos = CompositeScoringEngine.calculate_sentiment(positive_count=10, negative_count=0, total_classified=10)
    assert nsi_pos == 1.0
    assert score_pos == 35.0

    # All negative: NSI = -1.0 -> 0 points
    score_neg, nsi_neg = CompositeScoringEngine.calculate_sentiment(positive_count=0, negative_count=10, total_classified=10)
    assert nsi_neg == -1.0
    assert score_neg == 0.0

    # Balanced neutral: NSI = 0.0 -> 17.5 points
    score_neu, nsi_neu = CompositeScoringEngine.calculate_sentiment(positive_count=5, negative_count=5, total_classified=10)
    assert nsi_neu == 0.0
    assert score_neu == 17.5


def test_crisis_sla_zero_rumors_critical_rule():
    # CRITICAL RULE: If TotalRumorsIngested is 0, the engine must return 30 points (avoid division by zero)
    assert CompositeScoringEngine.calculate_crisis_sla(refuted_within_90m=0, total_rumors=0) == 30.0

    # 5 of 10 rumors refuted within 90 mins -> 15.0 points
    assert CompositeScoringEngine.calculate_crisis_sla(refuted_within_90m=5, total_rumors=10) == 15.0

    # 10 of 10 rumors refuted within 90 mins -> 30.0 points
    assert CompositeScoringEngine.calculate_crisis_sla(refuted_within_90m=10, total_rumors=10) == 30.0
