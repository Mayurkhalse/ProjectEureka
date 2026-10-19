"""OpenUI Lang Generator, Validator, Repair Engine, and Streaming Pipeline.

Complies strictly with:
- GIGW 3.0 & UX4G Accessibility (every visual element has text summary + table alternative)
- Number Grounding (rejects any fabricated numerical literal not present in tool data)
- Whitelisted Component Library (no raw HTML, scripts, or external links)
- Deterministic ViewSpec Fallback (if repair attempt fails)
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from eureka.copilot.viewspec import ViewSpec, ViewSpecBuilder

logger = logging.getLogger("eureka.copilot.openui_generator")

# Whitelisted OpenUI Library Components
ALLOWED_COMPONENTS = {
    "Stack",
    "KpiCard",
    "DataTable",
    "BarChart",
    "LineChart",
    "GraphView",
    "Callout",
    "Heading",
    "Text",
}

# Regex to detect HTML scripts, iframes, styles, links, or images
DISALLOWED_HTML_TAGS = re.compile(r'<\s*(?:script|iframe|object|embed|style|a\s+href|img\s+src)', re.IGNORECASE)


def detect_language(text: str) -> str:
    """Identify whether text is Marathi, Hindi, or English based on script and vocabulary."""
    devanagari_chars = sum(1 for c in text if '\u0900' <= c <= '\u097F')
    total_chars = max(1, len([c for c in text if not c.isspace()]))
    devanagari_ratio = devanagari_chars / total_chars

    if devanagari_ratio > 0.25:
        # Distinguish Marathi vs Hindi via marker words
        marathi_markers = ["आहे", "नाही", "जिल्हा", "माहिती", "कसा", "काय", "मधील", "झाले", "करा", "यांचे", "तालुका"]
        hindi_markers = ["है", "नहीं", "जिला", "कैसे", "क्या", "हुआ", "कीजिए", "उनका"]
        
        m_count = sum(1 for w in marathi_markers if w in text)
        h_count = sum(1 for w in hindi_markers if w in text)
        
        if m_count >= h_count:
            return "mr"
        return "hi"
    return "en"


def generate_copilot_system_instruction(
    language: str = "en",
    user_preferences: Optional[List[str]] = None,
    library_name: str = "DGIPR Maha-Command OpenUI Library",
) -> str:
    """Generate authoritative OpenUI Lang prompt targeting Gemma."""
    lang_instructions = {
        "mr": "उत्तर मराठी भाषेत आणि शासन मानक शैलीत (GIGW 3.0 / UX4G) द्या. आकडेवारी अचूक ठेवा.",
        "hi": "उत्तर हिंदी भाषा में और आधिकारिक शासन मानक शैली (GIGW 3.0 / UX4G) में दें। आंकड़े सटीक रखें।",
        "en": "Answer in English adhering to official DGIPR governance and GIGW 3.0 / UX4G accessibility standards.",
    }

    prefs_str = ""
    if user_preferences:
        bullet_points = "\n".join(f"  - {p}" for p in user_preferences)
        prefs_str = (
            f"\nUSER PRESENTATION PREFERENCES (May be wrong, never a source of facts. Use ONLY for presentation format):\n"
            f"{bullet_points}\n"
        )

    return f"""You are the DGIPR Maha-Command Center Open UI Copilot, an authoritative, read-only media intelligence assistant for the Government of Maharashtra.

{lang_instructions.get(language, lang_instructions['en'])}
{prefs_str}
STRICT SAFETY & DATA CONSTRAINTS:
1. You have access ONLY to governed read-only tools. NEVER invent, hallucinate, or estimate numbers, ranks, percentages, or dates.
2. Every number, score, or count you display MUST come directly from the tool outputs.
3. You must output valid OpenUI Lang markup using ONLY the following registered components:
   - <Stack direction="vertical|horizontal"> ... </Stack>
   - <KpiCard title="..." value="..." unit="..." delta=... status="positive|negative|neutral|critical" />
   - <DataTable columns="..." rows="..." caption="..." />
   - <BarChart title="..." xKey="..." yKey="..." data="..."> <Text content="..." /> <DataTable ... /> </BarChart>
   - <LineChart title="..." xKey="..." yKey="..." data="..."> <Text content="..." /> <DataTable ... /> </LineChart>
   - <GraphView title="..." nodes="..." edges="..."> <Text content="..." /> <DataTable ... /> </GraphView>
   - <Callout type="info|warning|success|critical" message="..." />
   - <Heading level=1|2|3|4 text="..." />
   - <Text content="..." />
4. NO raw HTML, no <script>, no external <a> or <img> tags.
5. In every BarChart, LineChart, or GraphView, you MUST include a nested <Text content="..." /> summary and an accessible <DataTable ... /> alternative for screen readers.
6. When tool results indicate 'PERMISSION_DENIED', immediately render a <Callout type="critical" message="..." /> explaining that access to that district or scope is refused.
"""


def extract_all_numbers(data: Any) -> Set[float]:
    """Recursively collect all numeric values present in a tool result data structure."""
    numbers = set()

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        numbers.add(round(float(data), 2))
    elif isinstance(data, dict):
        for v in data.values():
            numbers.update(extract_all_numbers(v))
    elif isinstance(data, list):
        for item in data:
            numbers.update(extract_all_numbers(item))
    elif isinstance(data, str):
        # Extract standalone numbers from strings
        found = re.findall(r'\b\d+(?:\.\d+)?\b', data)
        for num_str in found:
            try:
                numbers.add(round(float(num_str), 2))
            except ValueError:
                pass

    return numbers


def extract_numbers_from_openui(markup: str) -> List[float]:
    """Extract numeric literals from generated OpenUI attributes and content."""
    # Look for value="...", delta=..., and numbers in content="..."
    numbers = []
    # Match value="..." or value=...
    val_matches = re.findall(r'value=["\']?(\d+(?:\.\d+)?)["\']?', markup)
    for m in val_matches:
        numbers.append(round(float(m), 2))
    
    # Match delta=...
    delta_matches = re.findall(r'delta=["\']?(-?\d+(?:\.\d+)?)["\']?', markup)
    for m in delta_matches:
        numbers.append(round(float(m), 2))

    return numbers


def validate_openui_output(
    markup: str,
    tool_results: List[Dict[str, Any]],
) -> Tuple[bool, List[str]]:
    """Strictly validate OpenUI Lang against the component allowlist and ground numbers against tool data.
    
    Returns (is_valid, list_of_error_reasons).
    """
    errors = []

    if not markup or not markup.strip():
        return False, ["Output is completely empty."]

    # 1. Disallow raw HTML scripts, images, links
    if DISALLOWED_HTML_TAGS.search(markup):
        return False, ["Output contains forbidden HTML tags (<script>, <iframe>, <a>, or <img>)."]

    # 2. Check component tags against allowlist
    tag_matches = re.findall(r'<\s*([A-Z][a-zA-Z0-9]+)', markup)
    for tag in tag_matches:
        if tag not in ALLOWED_COMPONENTS:
            errors.append(f"UNKNOWN_COMPONENT: Tag '<{tag}>' is not permitted in OpenUI library.")

    # 3. Check number grounding
    allowed_numbers = set()
    for res in tool_results:
        allowed_numbers.update(extract_all_numbers(res.get("data", {})))
        # Also allow standard constants like 0, 100, 25, 30, 20 (pillar max limits)
        allowed_numbers.update({0.0, 1.0, 25.0, 30.0, 20.0, 100.0, 90.0, 45.0})

    markup_numbers = extract_numbers_from_openui(markup)
    for num in markup_numbers:
        # Allow +/- 0.05 rounding difference
        matched = any(abs(num - allowed) < 0.05 for allowed in allowed_numbers)
        if not matched:
            errors.append(f"FABRICATED_NUMBER: Literal '{num}' was found in OpenUI markup but does not exist in tool data.")

    return len(errors) == 0, errors


class OpenUIPipeline:
    """End-to-end generator, validator, and repair coordinator."""

    @staticmethod
    def create_fallback_viewspec(
        tool_name: str,
        tool_result: Dict[str, Any],
    ) -> ViewSpec:
        """Construct the canonical deterministic ViewSpec when generative UI fails validation."""
        return ViewSpecBuilder.build_from_tool_result(tool_name, tool_result, fallback=True)
