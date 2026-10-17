"""Cloud NLP Evaluator for Project EUREKA.

Calls Hugging Face Serverless Inference API for MuRIL (Sentiment/Entailment)
and Groq for Llama 3 (Crisis SLA reasoning).
"""

import json
import logging
import os
import re
import requests
from typing import Optional
from dotenv import find_dotenv, load_dotenv
from groq import Groq

# Load environment variables from .env
load_dotenv(find_dotenv(usecwd=True))

logger = logging.getLogger(__name__)

HF_TOKEN = os.environ.get("HF_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

# Hugging Face Inference Endpoints
# Using a standard sentiment model as a proxy for MuRIL civic sentiment mapping
HF_SENTIMENT_API = "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest"
HF_ROUTER_API = "https://router.huggingface.co/hf-inference/models/cardiffnlp/twitter-roberta-base-sentiment-latest"


def evaluate_sentiment_cloud(text: str) -> float:
    """Calls Hugging Face Inference API to get a sentiment score (-1.0 to 1.0).

    Falls back gracefully to cloud LLM or heuristic evaluation if HF endpoint is unreachable
    or quota-limited.
    """
    token = os.environ.get("HF_TOKEN") or HF_TOKEN
    clean_text = (text or "").strip()
    if not clean_text:
        return 0.0

    # 1. Primary: Try Hugging Face Serverless Endpoints
    if token:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"inputs": clean_text[:2000]}
        for endpoint in [HF_SENTIMENT_API, HF_ROUTER_API]:
            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    results = response.json()
                    if isinstance(results, list) and len(results) > 0 and isinstance(results[0], list):
                        results = results[0]
                    if isinstance(results, list) and len(results) > 0 and isinstance(results[0], dict):
                        score_map = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
                        best_match = max(results, key=lambda x: x.get("score", 0.0))
                        label = best_match.get("label", "").lower()
                        return score_map.get(label, 0.0)
            except Exception as e:
                logger.debug("HF endpoint %s error: %s", endpoint, e)

    # 2. Resilient Cloud Fallback via Groq if HF is unavailable/quota-limited
    groq_key = os.environ.get("GROQ_API_KEY") or GROQ_API_KEY
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            prompt = (
                "Analyze the sentiment of this news excerpt. "
                "Respond strictly with a single decimal number between -1.0 (very negative) "
                "and 1.0 (very positive), where 0.0 is neutral.\n\n"
                f"Text: {clean_text[:1500]}"
            )
            # Try active models
            for candidate_model in ["llama3-8b-8192", "qwen/qwen3.8-27b", "openai/gpt-oss-20b"]:
                try:
                    res = client.chat.completions.create(
                        messages=[{"role": "user", "content": prompt}],
                        model=candidate_model,
                        temperature=0.0,
                        max_tokens=8,
                    )
                    raw_val = res.choices[0].message.content.strip()
                    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", raw_val)
                    if match:
                        score = float(match.group(0))
                        return max(-1.0, min(1.0, score))
                except Exception:
                    continue
        except Exception as e:
            logger.warning("Groq sentiment fallback failed: %s", e)

    return 0.0


_WORKING_GROQ_MODEL: Optional[str] = None


def evaluate_crisis_sla_groq(district: str, text: str) -> bool:
    """Calls Groq Llama 3 to determine if an article successfully refutes a rumor."""
    global _WORKING_GROQ_MODEL
    api_key = os.environ.get("GROQ_API_KEY") or GROQ_API_KEY
    clean_text = (text or "").strip()
    if not api_key or not clean_text:
        return False

    prompt = (
        f"Analyze this article from {district}. Does it explicitly feature a government "
        "official refuting or resolving a crisis/rumor? Output strictly 'true' or 'false'.\n\n"
        f"Article: {clean_text[:2000]}"
    )

    client = Groq(api_key=api_key)

    # If we already identified a functioning model on this account, use it directly
    if _WORKING_GROQ_MODEL:
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=_WORKING_GROQ_MODEL,
                temperature=0.0,
                max_tokens=10,
            )
            result = response.choices[0].message.content.strip().lower()
            return "true" in result
        except Exception:
            _WORKING_GROQ_MODEL = None

    # Prefer llama3-8b-8192 as specified; gracefully fall back if model is decommissioned
    candidate_models = [
        "llama3-8b-8192",
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "qwen/qwen3.8-27b",
        "openai/gpt-oss-20b",
    ]

    for model_name in candidate_models:
        try:
            response = client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model=model_name,
                temperature=0.0,
                max_tokens=10,
            )
            result = response.choices[0].message.content.strip().lower()
            _WORKING_GROQ_MODEL = model_name
            return "true" in result
        except Exception as e:
            err_str = str(e)
            if "decommissioned" in err_str or "model_not_found" in err_str or "404" in err_str or "400" in err_str:
                logger.debug("Model %s unavailable, falling back...", model_name)
                continue
            logger.error("Groq API Error on %s: %s", model_name, e)
            break

    return False

