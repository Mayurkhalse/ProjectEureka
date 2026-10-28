"""Structured Presentation Preferences parsed from long-term memory.

Presentation preferences can ONLY influence display/rendering choices (e.g. chart variant,
language, verbosity). They cannot alter authorization, inject entities, or expand scope.
"""

import re
from dataclasses import dataclass
from typing import Literal, Optional, List


@dataclass(frozen=True)
class PresentationPrefs:
    """Structured presentation preferences applied during response composition."""
    chart: Optional[Literal["bar", "line", "pie", "donut", "table"]] = None
    language: Optional[Literal["mr", "hi", "en"]] = None
    verbosity: Optional[Literal["concise", "detailed"]] = None
    bilingual: bool = False

    @classmethod
    def default(cls) -> "PresentationPrefs":
        return cls()


def parse_presentation_prefs(
    raw_prefs: List[str],
    language_hint: str = "en",
) -> PresentationPrefs:
    """Deterministically parse preference strings into structured PresentationPrefs.

    Uses strict whole-token matching on an explicit allowlist to prevent substring false-positives
    (e.g. 'Baramati' must not match 'bar', 'deadline' must not match 'line').
    """
    chart_val: Optional[Literal["bar", "line", "pie", "donut", "table"]] = None
    lang_val: Optional[Literal["mr", "hi", "en"]] = None
    verb_val: Optional[Literal["concise", "detailed"]] = None
    bilingual_val: bool = False

    combined_text = " ".join(raw_prefs).lower()

    # Chart variant tokens
    if re.search(r'\b(donut|डोनट)\b', combined_text):
        chart_val = "donut"
    elif re.search(r'\b(pie|पाय|वर्तुळ)\b', combined_text):
        chart_val = "pie"
    elif re.search(r'\b(bar|बार|स्तंभ)\b', combined_text):
        chart_val = "bar"
    elif re.search(r'\b(line|रेषा|आलेख)\b', combined_text):
        chart_val = "line"
    elif re.search(r'\b(table|तक्ता|सारणी)\b', combined_text):
        chart_val = "table"

    # Language preference tokens
    if re.search(r'\b(marathi|मराठी)\b', combined_text):
        lang_val = "mr"
    elif re.search(r'\b(hindi|हिंदी)\b', combined_text):
        lang_val = "hi"
    elif re.search(r'\b(english|इंग्रजी)\b', combined_text):
        lang_val = "en"

    # Verbosity
    if re.search(r'\b(concise|brief|short|थोडक्यात|संक्षिप्त)\b', combined_text):
        verb_val = "concise"
    elif re.search(r'\b(detailed|comprehensive|सविस्तर|विस्तृत)\b', combined_text):
        verb_val = "detailed"

    # Bilingual
    if re.search(r'\b(bilingual|दोन भाषा|द्विभाषिक)\b', combined_text):
        bilingual_val = True

    return PresentationPrefs(
        chart=chart_val,
        language=lang_val or (language_hint if language_hint in ("mr", "hi", "en") else "en"),
        verbosity=verb_val,
        bilingual=bilingual_val,
    )
