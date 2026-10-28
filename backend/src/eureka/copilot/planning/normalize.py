"""Text normalization, digit folding, Devanagari phonetic folding, and tokenization.

Applied uniformly to queries and gazetteer aliases so comparisons are exact.
"""

import re
import unicodedata
from typing import List

# Devanagari and Arabic-Indic digit translation table
_DIGIT_MAP = str.maketrans({
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})

# Devanagari phonetic folding table (§6.2 of POLICYENGINE.md)
_PHONETIC_FOLD_MAP = str.maketrans({
    "ळ": "ल",  # धुळे -> धुले
    "श": "स",  # नाशिक -> नासिक
    "ष": "स",
    "ण": "न",  # ठाणे -> ठाने
    "ऩ": "न",
    "ऱ": "र",  # साताऱ्यात -> सातारा
    "ी": "ि",  # vowel length variants
    "ू": "ु",
    "ँ": "ं",  # chandrabindu -> anusvara
})

_NUKTA = "\u093C"
_ZERO_WIDTH_RE = re.compile(r"[\u200B\u200C\u200D\u200E\u200F\uFEFF]")


def fold_devanagari(text: str) -> str:
    """Apply phonetic folding and drop nukta for robust Devanagari matching."""
    if not text:
        return ""
    # Drop nukta
    t = text.replace(_NUKTA, "")
    # Apply phonetic fold
    return t.translate(_PHONETIC_FOLD_MAP)


def normalize_text(text: str, *, apply_phonetic_fold: bool = True) -> str:
    """Canonical normalization: NFC, zero-width strip, digit fold, whitespace collapse, lowercase.

    Returns the normalized string.
    """
    if not text:
        return ""

    # 1. Unicode NFC
    t = unicodedata.normalize("NFC", text)

    # 2. Strip zero-width characters
    t = _ZERO_WIDTH_RE.sub("", t)

    # 3. Translate native digits to ASCII digits
    t = t.translate(_DIGIT_MAP)

    # 4. Lowercase ASCII characters
    t = t.lower()

    # 5. Optional Devanagari phonetic folding
    if apply_phonetic_fold:
        t = fold_devanagari(t)

    # 6. Collapse multiple whitespaces
    t = re.sub(r"\s+", " ", t).strip()

    return t


def tokenize(text: str) -> List[str]:
    """Tokenize normalized text on whitespace and punctuation."""
    if not text:
        return []
    # Retain Devanagari characters, alphanumeric characters, and hyphens
    tokens = re.findall(r"[\u0900-\u097F\w-]+", text)
    return [t for t in tokens if t]
