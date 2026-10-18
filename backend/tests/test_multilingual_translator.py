"""Unit tests for Multilingual Indic Translation & Normalization Engine (Google AI Studio)."""

import json
from unittest.mock import MagicMock, patch
import pytest

from eureka.llm.multilingual_translator import (
    translate_and_normalize_indic,
    translate_and_normalize_indic_async,
    _fallback_translation,
)


def test_translate_fallback_when_empty():
    res = translate_and_normalize_indic("")
    assert res["detected_language"] == "en"
    assert "english_translation" in res

    res_none = translate_and_normalize_indic(None)
    assert res_none["detected_language"] == "en"


def test_translate_fallback_indic_detection():
    sample = "बीड जिल्ह्यातील सर्व पीक विमा दावे रद्द"
    res = _fallback_translation(sample)
    assert res["detected_language"] == "mr"
    assert res["dialect_region"] == "Standard Marathi"
    assert res["extracted_district_code"] == "MH-23"
    assert res["marathi_translation"] == sample


def test_translate_mocked_gemini_success():
    mock_payload = {
        "detected_language": "mr",
        "dialect_region": "Marathwada",
        "marathi_translation": "बीड जिल्ह्यातील सर्व पीक विमा दावे रद्द",
        "english_translation": "All crop insurance claims in Beed district cancelled",
        "extracted_district_code": "MH-23",
        "extracted_department": "Agriculture Department",
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [{
            "content": {
                "parts": [{"text": json.dumps(mock_payload)}]
            }
        }]
    }

    with patch("eureka.llm.multilingual_translator.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"GOOGLE_STUDIO_API_KEY": "test_key"}):
            res = translate_and_normalize_indic("बीड जिल्ह्यातील सर्व पीक विमा दावे रद्द")

            assert res["detected_language"] == "mr"
            assert res["extracted_district_code"] == "MH-23"
            assert "crop insurance" in res["english_translation"].lower()
            assert res["extracted_department"] == "Agriculture Department"


def test_translate_mocked_gemini_error_resilient_fallback():
    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    with patch("eureka.llm.multilingual_translator.httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        with patch.dict("os.environ", {"GOOGLE_STUDIO_API_KEY": "test_key"}):
            res = translate_and_normalize_indic("Thane water supply disruption")
            # Should not raise exception, falls back safely
            assert res["detected_language"] == "en"
            assert res["extracted_district_code"] == "MH-03"
            assert "Thane" in res["english_translation"]
