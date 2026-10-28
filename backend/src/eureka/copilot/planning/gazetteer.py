"""Gazetteer and Entity Resolution for Districts and Divisions.

Resolves Marathi, Hindi, English, and Romanized district/division entities,
handles grammatical inflections and suffixes, and applies homonym blocking guards.
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Tuple

from eureka.core.reference_data import DISTRICTS, DIVISIONS, DISTRICT_ALIASES
from eureka.copilot.planning.normalize import normalize_text, tokenize
from eureka.copilot.policy.principal import PolicyPrincipal, ALL_DISTRICT_CODES


class EntityKind(str, Enum):
    DISTRICT = "district"
    DIVISION = "division"
    POSSESSIVE = "possessive"


def get_district_name(code: str) -> str:
    """Resolve MH-XX code or DIV-XXX to English name, e.g. MH-21 -> Nashik."""
    for d in DISTRICTS:
        if d[0] == code:
            return d[2]
    for div in DIVISIONS:
        if div[0] == code:
            return div[1]
    return code


@dataclass(frozen=True)
class EntityMatch:
    code: str                  # MH-XX for district, DIV-XXX for division
    name_en: str
    span: Tuple[int, int]
    kind: EntityKind
    raw_text: str
    defaulted_scope: bool = False


# Known Marathi / Hindi grammatical inflections / postposition suffixes
DEVANAGARI_SUFFIXES = [
    "्यांचा", "्यांची", "्यांचे", "्यांच्या",
    "्याचा", "्याची", "्याचे", "याच्या", "याची",
    "्याला", "मध्ये", "मधील", "मधिल", "तील", "च्या", "ला", "ना",
    "चा", "ची", "चे", "ात", "्यात", "त", "ने", "वरून"
]
DEVANAGARI_SUFFIXES_NORM = {normalize_text(s) for s in DEVANAGARI_SUFFIXES} | set(DEVANAGARI_SUFFIXES)

# Homonym guards: alias -> set of normalized preceding tokens that block matching
HOMONYM_BLOCKERS: dict[str, set[str]] = {
    "ठाणे": {"पोलीस", "पोलिस", "police", "थाना"},
    "ठाने": {"पोलीस", "पोलिस", "police", "थाना"},
    "thane": {"police"},
}

# Possessive triggers for principal's district
POSSESSIVE_PATTERNS = [
    r"\b(my\s+district)\b",
    r"\b(our\s+district)\b",
    r"(माझा\s+जिल्हा)",
    r"(आमचा\s+जिल्हा)",
    r"(माझ्या\s+जिल्ह्यात)",
    r"(आमच्या\s+जिल्ह्यात)",
    r"(मेरा\s+जिला)",
    r"(हमारे\s+जिले)",
]

# Additional curated aliases to supplement reference_data without mutating core files
EXTRA_DISTRICT_ALIASES = [
    ("धुले", "MH-23"),        # Hindi spelling
    ("धुळे", "MH-23"),
    ("dhule", "MH-23"),
    ("नासिक", "MH-21"),       # Hindi spelling
    ("नाशिक", "MH-21"),
    ("nashik", "MH-21"),
    ("nasik", "MH-21"),
    ("ठाने", "MH-04"),        # Hindi spelling
    ("thane", "MH-04"),
    ("ठाणे", "MH-04"),
    ("पुणे", "MH-07"),
    ("poona", "MH-07"),
    ("pune", "MH-07"),
    ("सातारा", "MH-08"),
    ("सातार", "MH-08"),
    ("satara", "MH-08"),
    ("अहिल्यानगर", "MH-25"),
    ("अहमदनगर", "MH-25"),
    ("ahilyanagar", "MH-25"),
    ("ahmednagar", "MH-25"),
    ("छत्रपती संभाजीनगर", "MH-17"),
    ("संभाजीनगर", "MH-17"),
    ("औरंगाबाद", "MH-17"),
    ("aurangabad", "MH-17"),
    ("धाराशिव", "MH-14"),
    ("उस्मानाबाद", "MH-14"),
    ("osmanabad", "MH-14"),
    ("dhoole", "MH-23"),
    ("poone", "MH-07"),
    ("nashk", "MH-21"),
    ("thne", "MH-04"),
    ("solapr", "MH-09"),
    ("washm", "MH-28"),
    ("ahmednagr", "MH-25"),
    ("kolhapr", "MH-10"),
    ("जलगांव", "MH-22"),
    ("जलगाँव", "MH-22"),
    ("jalgaon", "MH-22"),
]


class Gazetteer:
    """Precomputed gazetteer lookup index built at module import."""

    def __init__(self):
        # District aliases: normalized_alias -> (district_code, name_en)
        self.district_aliases: List[Tuple[str, str, str]] = []

        # Division aliases: normalized_alias -> (division_code, name_en)
        self.division_aliases: List[Tuple[str, str, str]] = []

        self._build_index()

    def _build_index(self):
        seen_dist = set()

        # 1. From DISTRICTS
        for d in DISTRICTS:
            code = d[0]
            name_en = d[2]
            name_mr = d[3]
            former = d[4]

            for raw in [name_en, name_mr, former]:
                if raw:
                    norm = normalize_text(raw)
                    if (norm, code) not in seen_dist:
                        self.district_aliases.append((norm, code, name_en))
                        seen_dist.add((norm, code))

        # 2. From DISTRICT_ALIASES
        for alias_tuple in DISTRICT_ALIASES:
            raw = alias_tuple[0]
            code = alias_tuple[1]
            norm = normalize_text(raw)
            name_en = next((d[2] for d in DISTRICTS if d[0] == code), code)
            if (norm, code) not in seen_dist:
                self.district_aliases.append((norm, code, name_en))
                seen_dist.add((norm, code))

        # 3. From EXTRA_DISTRICT_ALIASES
        for raw, code in EXTRA_DISTRICT_ALIASES:
            norm = normalize_text(raw)
            name_en = next((d[2] for d in DISTRICTS if d[0] == code), code)
            if (norm, code) not in seen_dist:
                self.district_aliases.append((norm, code, name_en))
                seen_dist.add((norm, code))

        # 4. Division aliases
        seen_div = set()
        for div in DIVISIONS:
            div_code = div[0]
            name_en = div[1]
            name_mr = div[2]

            for raw in [
                name_en,
                f"{name_en} division",
                f"{name_en} region",
                name_mr,
                f"{name_en} विभाग",
            ]:
                norm = normalize_text(raw)
                if (norm, div_code) not in seen_div:
                    self.division_aliases.append((norm, div_code, name_en))
                    seen_div.add((norm, div_code))

        # Sort longest alias first for greedy matching
        self.district_aliases.sort(key=lambda x: len(x[0]), reverse=True)
        self.division_aliases.sort(key=lambda x: len(x[0]), reverse=True)


_GAZETTEER = Gazetteer()


def _is_stem_match(token: str, stem: str) -> bool:
    """Check if token equals stem plus a known Marathi inflectional suffix,
    including oblique grammatical forms (e.g. पुणे -> पुण्याची, धुळे -> धुळ्याचा).
    """
    if token.startswith(stem):
        suffix = token[len(stem):]
        if suffix in DEVANAGARI_SUFFIXES_NORM or not suffix:
            return True

    # Oblique stem for words ending in -े (e.g. पुणे -> पुण्या, धुळे -> धुळ्या, ठाणे -> ठाण्या)
    if stem.endswith("े"):
        oblique = stem[:-1] + "्या"
        norm_oblique = normalize_text(oblique)
        if token.startswith(norm_oblique) or token.startswith(oblique):
            prefix_len = len(norm_oblique) if token.startswith(norm_oblique) else len(oblique)
            suffix = token[prefix_len:]
            if suffix in DEVANAGARI_SUFFIXES_NORM or not suffix:
                return True

    # Oblique stem for words ending in -ारा (e.g. सातारा -> साताऱ्या)
    if stem.endswith("ारा"):
        oblique = stem[:-3] + "ाऱ्या"
        norm_oblique = normalize_text(oblique)
        if token.startswith(norm_oblique) or token.startswith(oblique):
            prefix_len = len(norm_oblique) if token.startswith(norm_oblique) else len(oblique)
            suffix = token[prefix_len:]
            if suffix in DEVANAGARI_SUFFIXES_NORM or not suffix:
                return True

    return False


def resolve_entities(
    query: str,
    principal: Optional[PolicyPrincipal] = None,
) -> List[EntityMatch]:
    """Extract and resolve all district and division entities from query text."""
    if not query:
        return []

    norm_query = normalize_text(query)
    tokens = tokenize(norm_query)
    matches: List[EntityMatch] = []
    consumed_spans: List[Tuple[int, int]] = []

    def span_overlaps(s_start: int, s_end: int) -> bool:
        for c_start, c_end in consumed_spans:
            if max(s_start, c_start) < min(s_end, c_end):
                return True
        return False

    # 1. Check explicit MH-XX codes (e.g. MH-04, MH21, mh 4)
    for m in re.finditer(r"\b(mh)[-\s]?(\d{1,2})\b", query, re.IGNORECASE):
        num = int(m.group(2))
        code = f"MH-{num:02d}"
        if code in ALL_DISTRICT_CODES:
            start, end = m.span()
            if not span_overlaps(start, end):
                name_en = next((d[2] for d in DISTRICTS if d[0] == code), code)
                matches.append(EntityMatch(
                    code=code,
                    name_en=name_en,
                    span=(start, end),
                    kind=EntityKind.DISTRICT,
                    raw_text=m.group(0),
                ))
                consumed_spans.append((start, end))

    # 2. Check division aliases first (e.g. 'Pune division' must NOT resolve to district Pune)
    for alias_norm, div_code, div_name in _GAZETTEER.division_aliases:
        # Check if alias appears in query
        if "division" in alias_norm or "विभाग" in alias_norm:
            pattern = r"\b" + re.escape(alias_norm) + r"\b"
            for m in re.finditer(pattern, norm_query):
                start, end = m.span()
                if not span_overlaps(start, end):
                    matches.append(EntityMatch(
                        code=div_code,
                        name_en=div_name,
                        span=(start, end),
                        kind=EntityKind.DIVISION,
                        raw_text=query[start:end] if end <= len(query) else alias_norm,
                    ))
                    consumed_spans.append((start, end))

    # 3. Check possessives ("my district", "माझा जिल्हा")
    for pat in POSSESSIVE_PATTERNS:
        for m in re.finditer(pat, query, re.IGNORECASE):
            start, end = m.span()
            if not span_overlaps(start, end):
                dist_code = principal.district_code if principal else None
                if dist_code:
                    name_en = next((d[2] for d in DISTRICTS if d[0] == dist_code), dist_code)
                    matches.append(EntityMatch(
                        code=dist_code,
                        name_en=name_en,
                        span=(start, end),
                        kind=EntityKind.POSSESSIVE,
                        raw_text=m.group(0),
                        defaulted_scope=True,
                    ))
                    consumed_spans.append((start, end))

    # 4. District aliases matching with word-boundary and suffix stem check
    for idx, token in enumerate(tokens):
        # Check homonym blockers for previous token
        prev_token = tokens[idx - 1] if idx > 0 else ""

        for alias_norm, code, name_en in _GAZETTEER.district_aliases:
            is_match = False
            # Check ASCII word match
            if re.search(r"[a-z]", alias_norm):
                if token == alias_norm:
                    is_match = True
            else:
                # Devanagari exact token match or stem inflection match
                if token == alias_norm or _is_stem_match(token, alias_norm):
                    is_match = True

            if is_match:
                # Apply homonym blocker (e.g. 'पोलीस ठाणे' blocks 'ठाणे')
                blockers = HOMONYM_BLOCKERS.get(alias_norm, set())
                if prev_token in blockers:
                    continue

                # Find span in query
                m = re.search(re.escape(token), norm_query)
                start = m.start() if m else 0
                end = m.end() if m else len(token)

                if not span_overlaps(start, end):
                    matches.append(EntityMatch(
                        code=code,
                        name_en=name_en,
                        span=(start, end),
                        kind=EntityKind.DISTRICT,
                        raw_text=token,
                    ))
                    consumed_spans.append((start, end))
                    break

    # 5. Fuzzy match fallback for unconsumed ASCII tokens with minor typos
    COMMON_NON_DISTRICTS = {
        "what", "when", "where", "which", "about", "there", "their",
        "show", "tell", "give", "please", "score", "table", "crisis",
        "trend", "rumor", "rumors", "views", "level", "state", "doing",
        "lately", "right", "good", "great", "better", "worst", "rank",
        "explain", "check", "news", "volume", "mood", "people", "think",
    }
    for idx, token in enumerate(tokens):
        if re.search(r"^[a-z]{4,}$", token) and token not in COMMON_NON_DISTRICTS:
            m_span = re.search(r"\b" + re.escape(token) + r"\b", norm_query)
            if m_span and not span_overlaps(m_span.start(), m_span.end()):
                import difflib
                ascii_candidates = [a[0] for a in _GAZETTEER.district_aliases if re.search(r"^[a-z\s]+$", a[0])]
                close = difflib.get_close_matches(token, ascii_candidates, n=1, cutoff=0.68)
                if close:
                    matched_alias = close[0]
                    for a_norm, c, n_en in _GAZETTEER.district_aliases:
                        if a_norm == matched_alias:
                            matches.append(EntityMatch(
                                code=c,
                                name_en=n_en,
                                span=(m_span.start(), m_span.end()),
                                kind=EntityKind.DISTRICT,
                                raw_text=token,
                            ))
                            consumed_spans.append((m_span.start(), m_span.end()))
                            break

    # Sort matches by appearance in query
    matches.sort(key=lambda x: x.span[0])
    return matches
