"""Unit tests for 100-Point Composite Index Scoring Engine in Project EUREKA."""

import pytest
from eureka.scoring.scoring_engine import CompositeScoringEngine


def test_volume_pillar_saturation():
    # 0 releases -> 0 points
    assert CompositeScoringEngine.calculate_volume(0) == 0.0

    # 150 releases -> 12.5 points
    assert CompositeScoringEngine.calculate_volume(150) == 12.5

    # 300 releases -> 25 points
    assert CompositeScoringEngine.calculate_volume(300) == 25.0

    # 500 releases -> capped at 25 points
    assert CompositeScoringEngine.calculate_volume(500) == 25.0


def test_tat_speed_pillar():
    # <= 45 minutes -> 25.0 points
    assert CompositeScoringEngine.calculate_tat(30.0) == 25.0
    assert CompositeScoringEngine.calculate_tat(45.0) == 25.0

    # >= 120 minutes -> 0.0 points
    assert CompositeScoringEngine.calculate_tat(120.0) == 0.0
    assert CompositeScoringEngine.calculate_tat(180.0) == 0.0

    # Midpoint: (45 + 120) / 2 = 82.5 minutes -> 12.5 points
    assert CompositeScoringEngine.calculate_tat(82.5) == 12.5


def test_sentiment_pillar_nsi_mapping():
    # All positive: NSI = 1.0 -> 25 points
    score_pos, nsi_pos = CompositeScoringEngine.calculate_sentiment(positive_count=10, negative_count=0, total_classified=10)
    assert nsi_pos == 1.0
    assert score_pos == 25.0

    # All negative: NSI = -1.0 -> 0 points
    score_neg, nsi_neg = CompositeScoringEngine.calculate_sentiment(positive_count=0, negative_count=10, total_classified=10)
    assert nsi_neg == -1.0
    assert score_neg == 0.0

    # Balanced neutral: NSI = 0.0 -> 12.5 points
    score_neu, nsi_neu = CompositeScoringEngine.calculate_sentiment(positive_count=5, negative_count=5, total_classified=10)
    assert nsi_neu == 0.0
    assert score_neu == 12.5


def test_crisis_sla_zero_rumors_critical_rule():
    # CRITICAL RULE: If TotalRumorsIngested is 0, the engine must return 25 points (avoid division by zero)
    assert CompositeScoringEngine.calculate_crisis_sla(refuted_within_90m=0, total_rumors=0) == 25.0

    # 5 of 10 rumors refuted within 90 mins -> 12.5 points
    assert CompositeScoringEngine.calculate_crisis_sla(refuted_within_90m=5, total_rumors=10) == 12.5

    # 10 of 10 rumors refuted within 90 mins -> 25.0 points
    assert CompositeScoringEngine.calculate_crisis_sla(refuted_within_90m=10, total_rumors=10) == 25.0
