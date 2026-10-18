"""Multilingual Indic Translation & Normalization Engine for Project EUREKA.

Calls Google AI Studio (gemini-flash-latest) via REST API to normalize regional Indic
dialects (Marathi, Varhadi, Ahirani, Konkani, Hindi) into official bilingual Devanagari
Marathi and English for GIGW 3.0 government compliance.
"""

import json
import logging
import os
import re
from typing import Any, Dict, Optional
import httpx
from dotenv import find_dotenv, load_dotenv

# Load credentials from .env
load_dotenv(find_dotenv(usecwd=True))

logger = logging.getLogger(__name__)

GOOGLE_STUDIO_API_KEY = os.environ.get("GOOGLE_STUDIO_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
GEMINI_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

# Standard district mapping for deterministic code extraction fallback
DISTRICT_CODE_MAP = {
    "mumbai city": "MH-01",
    "mumbai suburban": "MH-02",
    "thane": "MH-03",
    "palghar": "MH-04",
    "raigad": "MH-05",
    "ratnagiri": "MH-06",
    "sindhudurg": "MH-07",
    "kolhapur": "MH-09",
    "sangli": "MH-10",
    "satara": "MH-11",
    "pune": "MH-12",
    "solapur": "MH-13",
    "ahmednagar": "MH-14",
    "ahilyanagar": "MH-14",
    "nashik": "MH-15",
    "dhule": "MH-16",
    "nandurbar": "MH-17",
    "jalgaon": "MH-18",
    "chhatrapati sambhajinagar": "MH-19",
    "aurangabad": "MH-19",
    "jalna": "MH-20",
    "parbhani": "MH-21",
    "hingoli": "MH-22",
    "beed": "MH-23",
    "latur": "MH-24",
    "nanded": "MH-25",
    "dharashiv": "MH-26",
    "osmanabad": "MH-26",
    "buldhana": "MH-27",
    "akola": "MH-28",
    "washim": "MH-29",
    "amravati": "MH-30",
    "yavatmal": "MH-31",
    "wardha": "MH-32",
    "nagpur": "MH-33",
    "chandrapur": "MH-34",
    "bhandara": "MH-35",
    "gondia": "MH-36",
    "gadchiroli": "MH-37",
    # Devanagari Marathi names
    "मुंबई": "MH-01", "ठाणे": "MH-03", "पालघर": "MH-04", "रायगड": "MH-05",
    "रत्नागिरी": "MH-06", "सिंधुदुर्ग": "MH-07", "कोल्हापूर": "MH-09", "सांगली": "MH-10",
    "सातारा": "MH-11", "पुणे": "MH-12", "सोलापूर": "MH-13", "अहिल्यानगर": "MH-14",
    "अहमदनगर": "MH-14", "नाशिक": "MH-15", "धुळे": "MH-16", "नंदुरबार": "MH-17",
    "जळगाव": "MH-18", "छत्रपती संभाजीनगर": "MH-19", "संभाजीनगर": "MH-19", "औरंगाबाद": "MH-19",
    "जालना": "MH-20", "परभणी": "MH-21", "हिंगोली": "MH-22", "बीड": "MH-23",
    "लातूर": "MH-24", "नांदेड": "MH-25", "धाराशिव": "MH-26", "उस्मानाबाद": "MH-26",
    "बुलढाणा": "MH-27", "अकोला": "MH-28", "वाशिम": "MH-29", "अमरावती": "MH-30",
    "यवतमाळ": "MH-31", "वर्धा": "MH-32", "नागपूर": "MH-33", "चंद्रपूर": "MH-34",
    "भंडारा": "MH-35", "गोंदिया": "MH-36", "गडचिरोली": "MH-37",
}

SYS_PROMPT = (
    "You are an Indic linguistic intelligence parser for the Directorate General of Information "
    "and Public Relations (DGIPR), Government of Maharashtra.\n"
    "Analyze the provided text and output strictly a valid JSON object with zero conversational commentary.\n\n"
    "Expected JSON schema:\n"
    "{\n"
    '  "marathi_text": "Official Devanagari Marathi text for GIGW 3.0 bilingual compliance",\n'
    '  "english_text": "Crisp, bureaucratic English translation with zero filler",\n'
    '  "detected_dialect": "Standard Marathi | Varhadi | Ahirani | Marathwada | Konkani | Hindi | English",\n'
    '  "extracted_district_code": "MH-XX or null",\n'
    '  "detected_language": "mr | hi | en",\n'
    '  "extracted_department": "Official Maharashtra Dept Name or General Administration"\n'
    "}"
)


def _clean_json_response(raw_text: str) -> Dict[str, Any]:
    """Extracts and parses JSON from Gemini model output, stripping markdown fencing."""
    if not raw_text:
        return {}
    raw = raw_text.strip()
    # Strip ```json ... ``` or ``` ... ``` markdown fences
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw)
    if match:
        raw = match.group(1).strip()
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception as e:
        logger.warning("JSON parse failed on Gemini response: %s. Raw: %s", e, raw[:200])
    return {}


def _standardize_payload(data: Dict[str, Any], raw_fallback: str) -> Dict[str, Any]:
    """Ensures deterministic schema with both primary and backward-compatible keys."""
    marathi = data.get("marathi_text") or data.get("marathi_translation") or raw_fallback
    english = data.get("english_text") or data.get("english_translation") or raw_fallback
    dialect = data.get("detected_dialect") or data.get("dialect_region") or "Standard Marathi"
    district = data.get("extracted_district_code")

    # If district code not detected, perform fallback extraction
    if not district and raw_fallback:
        lower_text = raw_fallback.lower()
        for name, code in DISTRICT_CODE_MAP.items():
            if name in lower_text:
                district = code
                break

    dept = data.get("extracted_department") or "General Administration Department"
    lang = data.get("detected_language") or ("mr" if any("\u0900" <= ch <= "\u097f" for ch in marathi) else "en")

    return {
        "marathi_text": marathi,
        "english_text": english,
        "detected_dialect": dialect,
        "extracted_district_code": district,
        # Backward compatibility aliases
        "marathi_translation": marathi,
        "english_translation": english,
        "dialect_region": dialect,
        "detected_language": lang,
        "extracted_department": dept,
    }


def _fallback_translation(text: str) -> Dict[str, Any]:
    """Deterministic offline fallback if Gemini API is unreachable or rate limited."""
    clean = (text or "").strip()
    detected_lang = "en"
    if any("\u0900" <= ch <= "\u097f" for ch in clean):
        detected_lang = "mr"

    district_code = None
    lower_text = clean.lower()
    for name, code in DISTRICT_CODE_MAP.items():
        if name in lower_text:
            district_code = code
            break

    marathi = clean if detected_lang == "mr" else "माहिती व जनसंपर्क महासंचालनालय अधिकृत प्रसिद्धी पत्रक"
    english = clean if detected_lang == "en" else "DGIPR Official Press Communication"
    dialect = "Standard Marathi" if detected_lang == "mr" else "English"

    return {
        "marathi_text": marathi,
        "english_text": english,
        "detected_dialect": dialect,
        "extracted_district_code": district_code,
        # Backward compatibility aliases
        "detected_language": detected_lang,
        "dialect_region": dialect,
        "marathi_translation": marathi,
        "english_translation": english,
        "extracted_department": "General Administration Department",
    }


def translate_and_normalize_indic(text: str, source_hint: str = "auto") -> Dict[str, Any]:
    """Synchronous translation and Indic normalization via gemini-flash-latest.
    
    Returns strict JSON:
    {"marathi_text": "...", "english_text": "...", "detected_dialect": "...", "extracted_district_code": "MH-XX"}
    """
    clean_text = (text or "").strip()
    if not clean_text:
        return _fallback_translation("")

    api_key = os.environ.get("GOOGLE_STUDIO_API_KEY") or GOOGLE_STUDIO_API_KEY
    if not api_key:
        logger.warning("GOOGLE_STUDIO_API_KEY not configured, using deterministic fallback.")
        return _fallback_translation(clean_text)

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key,
    }

    user_query = f"{SYS_PROMPT}\n\nText to analyze:\n{clean_text[:4000]}"
    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(GEMINI_ENDPOINT, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        parsed = _clean_json_response(parts[0].get("text", ""))
                        if parsed:
                            return _standardize_payload(parsed, clean_text)
            else:
                logger.warning("Gemini API error %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("Failed to invoke gemini-flash-latest: %s", exc)

    return _fallback_translation(clean_text)


async def translate_and_normalize_indic_async(text: str, source_hint: str = "auto") -> Dict[str, Any]:
    """Asynchronous translation and Indic normalization via gemini-flash-latest."""
    clean_text = (text or "").strip()
    if not clean_text:
        return _fallback_translation("")

    api_key = os.environ.get("GOOGLE_STUDIO_API_KEY") or GOOGLE_STUDIO_API_KEY
    if not api_key:
        return _fallback_translation(clean_text)

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": api_key,
    }

    user_query = f"{SYS_PROMPT}\n\nText to analyze:\n{clean_text[:4000]}"
    payload = {
        "contents": [{"parts": [{"text": user_query}]}],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json",
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(GEMINI_ENDPOINT, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        parsed = _clean_json_response(parts[0].get("text", ""))
                        if parsed:
                            return _standardize_payload(parsed, clean_text)
    except Exception as exc:
        logger.warning("Async Gemini translation exception: %s", exc)

    return _fallback_translation(clean_text)
