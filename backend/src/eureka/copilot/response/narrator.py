"""Optional Prose Lane and Strict Narrative Validator.

Generates concise, verified factual executive summaries strictly from authorized OpResults.
Enforces:
  1. Plain-text only (no tags, links, or backticks).
  2. Numbers must be grounded to within 0.005 of values in that specific section's data.
  3. No ungrounded or out-of-scope district names permitted.
"""

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Set

from eureka.copilot.execution.results import OpResult
from eureka.copilot.planning.normalize import normalize_text
from eureka.copilot.gemma_client import get_gemma_client

logger = logging.getLogger("eureka.copilot.response.narrator")


def _extract_all_numbers(obj: Any) -> Set[float]:
    """Recursively extract numeric values from JSON-like object."""
    numbers: Set[float] = set()
    if isinstance(obj, (int, float)) and not isinstance(obj, bool):
        numbers.add(float(obj))
        # Also add percentage equivalent if between 0 and 1
        if 0.0 <= obj <= 1.0:
            numbers.add(round(float(obj) * 100, 2))
    elif isinstance(obj, str):
        # Ignore ISO dates and MH-XX
        s = re.sub(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}", " ", obj)
        s = re.sub(r"\bMH-\d{1,2}\b", " ", s, flags=re.IGNORECASE)
        for num in re.findall(r"-?\b\d+(?:\.\d+)?\b", s):
            try:
                numbers.add(float(num))
            except ValueError:
                pass
    elif isinstance(obj, list):
        for item in obj:
            numbers.update(_extract_all_numbers(item))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            numbers.update(_extract_all_numbers(v))
    return numbers


def validate_narrator_section(
    section_id: str,
    text: str,
    authorized_districts: Set[str],
    section_numbers: Set[float],
) -> bool:
    """Validate narrator prose for a single section with 0.005 tolerance (§8.4)."""
    if not text or not isinstance(text, str):
        return False

    # 1. Reject tags, markup, links, backticks, newlines, or length > 400
    if len(text) > 400:
        logger.warning("narrator.validation: text exceeds 400 chars")
        return False
    if re.search(r"[<>`\r\n]|https?://", text):
        logger.warning("narrator.validation: text contains illegal markup/url characters")
        return False

    # 2. Extract and ground all numbers against this section's data numbers
    prose_numbers: List[float] = []
    # Mask dates and district codes
    clean_text = re.sub(r"\b\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}", " ", text)
    clean_text = re.sub(r"\bMH-\d{1,2}\b", " ", clean_text, flags=re.IGNORECASE)
    for num_str in re.findall(r"-?\b\d+(?:\.\d+)?\b", clean_text):
        try:
            prose_numbers.append(float(num_str))
        except ValueError:
            pass

    for num in prose_numbers:
        # Check if number is within 0.005 of any number in section_numbers
        matched = False
        for valid_num in section_numbers:
            if abs(num - valid_num) <= 0.005:
                matched = True
                break
        if not matched:
            logger.warning("narrator.validation: ungrounded number %s in section %s", num, section_id)
            return False

    # 3. Ground districts: Every district mentioned in prose must be in authorized_districts
    from eureka.copilot.planning.gazetteer import resolve_entities
    mentioned_entities = resolve_entities(text)
    for ent in mentioned_entities:
        if ent.code.upper() not in authorized_districts:
            logger.warning(
                "narrator.validation: unauthorized district %s mentioned in section %s",
                ent.code,
                section_id,
            )
            return False

    return True


async def generate_narration(
    results: List[OpResult],
    language: str = "en",
    timeout_seconds: float = 4.0,
) -> Dict[str, str]:
    """Generate validated factual prose summaries for authorized OpResults only."""
    gemma = get_gemma_client()
    if not gemma.is_available():
        return {}

    # Build input payload ONLY from results with status == 'ok' (§8.4)
    sections_payload = []
    section_context: Dict[str, Dict[str, Any]] = {}

    for res in results:
        if res.status != "ok" or not res.data:
            continue
        sec_id = res.group
        if sec_id not in section_context:
            # Aggregate allowed districts and numbers for validation
            allowed_districts = set()
            if "district_code" in res.args:
                allowed_districts.add(str(res.args["district_code"]).upper())
            if "district_codes" in res.args and isinstance(res.args["district_codes"], list):
                allowed_districts.update(str(d).upper() for d in res.args["district_codes"])

            numbers = _extract_all_numbers(res.data)
            numbers.update(_extract_all_numbers(res.args))

            section_context[sec_id] = {
                "districts": allowed_districts,
                "numbers": numbers,
            }
            sections_payload.append({
                "section_id": sec_id,
                "tool": res.tool,
                "data": res.data,
            })

    if not sections_payload:
        return {}

    system_instruction = (
        "You write short factual summaries for a government officer.\n"
        "You are given JSON results for named sections.\n"
        "For each section write 1-2 plain-text sentences.\n"
        "Rules:\n"
        "- Use only numbers that appear in that section's data;\n"
        "- Never mention a district that is not in that section's data;\n"
        "- Do not compare sections;\n"
        "- No rankings or superlatives unless a rank field exists;\n"
        "- No markup, no links;\n"
        f"- Answer in {language}.\n"
        'Return ONLY valid JSON: {"summaries": [{"section_id": "...", "text": "..."}]}'
    )

    user_input = json.dumps({"sections": sections_payload}, default=str)

    try:
        response = await asyncio.wait_for(
            gemma.generate(
                system_instruction=system_instruction,
                contents=[{"role": "user", "parts": [{"text": user_input}]}],
            ),
            timeout=timeout_seconds,
        )

        candidates = response.get("candidates", [])
        if not candidates:
            return {}

        raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        # Parse JSON
        # Clean potential markdown fences
        clean_json = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
        data = json.loads(clean_json)

        validated_summaries: Dict[str, str] = {}
        for item in data.get("summaries", []):
            s_id = item.get("section_id")
            s_text = item.get("text", "").strip()
            if s_id in section_context and s_text:
                ctx = section_context[s_id]
                if validate_narrator_section(
                    section_id=s_id,
                    text=s_text,
                    authorized_districts=ctx["districts"],
                    section_numbers=ctx["numbers"],
                ):
                    validated_summaries[s_id] = s_text

        return validated_summaries

    except Exception as exc:
        logger.warning("narrator.error: %s", exc)
        return {}
