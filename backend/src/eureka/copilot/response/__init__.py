"""Response generation, composition, validation, and presentation preferences."""

from eureka.copilot.response.prefs import PresentationPrefs, parse_presentation_prefs
from eureka.copilot.response.notices import NOTICES, get_notice
from eureka.copilot.response.markup_scan import scan_markup, extract_numbers_from_markup
from eureka.copilot.response.narrator import generate_narration, validate_narrator_section
from eureka.copilot.response.composer import Section, compose

__all__ = [
    "PresentationPrefs",
    "parse_presentation_prefs",
    "NOTICES",
    "get_notice",
    "scan_markup",
    "extract_numbers_from_markup",
    "generate_narration",
    "validate_narrator_section",
    "Section",
    "compose",
]
