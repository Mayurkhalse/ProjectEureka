"""Unit and integration tests for Cloud NLP Evaluator and NEWS_API Celery Dispatch."""

import unittest
from unittest.mock import MagicMock, patch
import pytest

from eureka.llm.cloud_evaluator import (
    evaluate_sentiment_cloud,
    evaluate_crisis_sla_groq,
)
from NEWS_API import dispatch_to_celery


def test_evaluate_sentiment_cloud_fallback_when_empty():
    assert evaluate_sentiment_cloud("") == 0.0
    assert evaluate_sentiment_cloud(None) == 0.0


def test_evaluate_sentiment_cloud_mocked_hf():
    with patch.dict("os.environ", {"HF_TOKEN": "mock_hf_token"}), \
         patch("eureka.llm.cloud_evaluator.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [[
            {"label": "positive", "score": 0.95},
            {"label": "neutral", "score": 0.03},
            {"label": "negative", "score": 0.02},
        ]]
        mock_post.return_value = mock_resp

        score = evaluate_sentiment_cloud("Great government initiative for rural water access.")
        assert score == 1.0


def test_evaluate_crisis_sla_groq_mocked():
    with patch.dict("os.environ", {"GROQ_API_KEY": "mock_groq_key"}), \
         patch("eureka.llm.cloud_evaluator.Groq") as mock_groq_cls:
        mock_client = MagicMock()
        mock_groq_cls.return_value = mock_client
        mock_completion = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "true"
        mock_completion.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_completion

        res = evaluate_crisis_sla_groq("Thane", "District collector debunked water contamination rumor.")
        assert res is True


def test_dispatch_to_celery_schema_mapping():
    scraped_articles = [
        {
            "title": "Road Repair Completed in Thane",
            "url": "https://example.com/news1",
            "scrape_status": "success",
            "scraped_content": "The public works department confirmed all repairs were finalized yesterday.",
            "published_at": "2026-10-17T08:00:00Z",
        },
        {
            "title": "Failed Scrape",
            "url": "https://example.com/news2",
            "scrape_status": "failed",
            "scraped_content": "",
        },
    ]

    with patch("NEWS_API.evaluate_sentiment_cloud", return_value=0.75), \
         patch("NEWS_API.evaluate_crisis_sla_groq", return_value=True), \
         patch("NEWS_API.process_ingestion_chunk.delay") as mock_delay:

        dispatch_to_celery(scraped_articles, "Thane")

        assert mock_delay.called
        args, _ = mock_delay.call_args
        records = args[0]
        assert len(records) == 1
        record = records[0]
        assert record["district"] == "Thane"
        assert record["event_type"] == "News Article"
        assert record["sentiment_score"] == 0.75
        assert record["crisis_resolved"] is True
        assert record["turnaround_time_mins"] == 30.0
        assert "PWD" in record["english_content"] or "repairs" in record["english_content"]
        assert "record_id" in record
