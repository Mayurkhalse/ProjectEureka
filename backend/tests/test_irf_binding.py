"""Unit tests for SemIf-OpenJev IRF Binding and Normalization in Project EUREKA."""

import uuid
from datetime import datetime, timezone
import pytest

from eureka.irf_binding.engine import (
    OpenJevEvaluation,
    SemIfOpenJevBindingEngine,
    TextNormalizer,
)
from eureka.models.enums import BindingDecisionType, DetectedLanguage


def test_language_and_script_detection_marathi():
    marathi_text = "महाराष्ट्र शासनाने दुष्काळ निवारणासाठी विशेष पॅकेज जाहीर केले आहे."
    lang, script = TextNormalizer.detect_language_and_script(marathi_text)
    assert lang == DetectedLanguage.MARATHI
    assert script == "Devanagari"


def test_language_and_script_detection_english():
    english_text = "Chief Minister announces infrastructure projects for Vidarbha region."
    lang, script = TextNormalizer.detect_language_and_script(english_text)
    assert lang == DetectedLanguage.ENGLISH
    assert script == "Latin"


def test_openjev_primitives_decision_logic():
    # Identical texts -> Choice (> 0.90)
    text_a = "Cabinet sanctions 500 crore rupees for medical colleges in Marathwada region."
    text_b = "Cabinet sanctions 500 crore rupees for medical colleges in Marathwada region."
    eval_choice = SemIfOpenJevBindingEngine.evaluate_openjev(text_a, text_b)
    assert eval_choice.primitive == "Choice"
    assert eval_choice.decision == BindingDecisionType.SAME_EVENT
    assert eval_choice.similarity_score >= 0.90

    # Completely different texts -> Noul (< 0.70)
    text_c = "Traffic advisory issued for Bandra Kurla Complex due to political rally."
    eval_noul = SemIfOpenJevBindingEngine.evaluate_openjev(text_a, text_c)
    assert eval_noul.primitive == "Noul"
    assert eval_noul.decision == BindingDecisionType.NEW_EVENT
    assert eval_noul.similarity_score < 0.70
