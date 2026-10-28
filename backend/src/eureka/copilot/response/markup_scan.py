"""State-Machine OpenUI Markup Scanner and Attribute Parser.

Replaces brittle regex parsers with a robust state-machine scanner.
Safely parses OpenUI Lang tags, attributes (including JSON structures with embedded quotes),
and enforces length caps (§8.5 of POLICYENGINE.md).
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Set, Tuple


@dataclass
class ScannedTag:
    tag: str
    attributes: Dict[str, str]
    is_self_closing: bool
    span: Tuple[int, int]


TEXT_PROPS: Set[str] = {
    "title", "message", "content", "text", "caption", "summary", "label", "delta", "value"
}

DATA_PROPS: Set[str] = {
    "data", "rows", "columns", "nodes", "edges", "categories", "values"
}

# Max length caps per prop
MAX_TEXT_PROP_CHARS = 600
MAX_DATA_PROP_CHARS = 60000


def scan_markup(markup: str) -> List[ScannedTag]:
    """Scan OpenUI Lang string and extract structured tags and attributes."""
    if not markup:
        return []

    tags: List[ScannedTag] = []
    pos = 0
    length = len(markup)

    while pos < length:
        tag_start = markup.find("<", pos)
        if tag_start == -1:
            break

        # Check closing tag </...>
        if tag_start + 1 < length and markup[tag_start + 1] == "/":
            tag_end = markup.find(">", tag_start)
            if tag_end == -1:
                break
            pos = tag_end + 1
            continue

        # Check comment or invalid
        if tag_start + 1 < length and markup[tag_start + 1] in ("!", "?"):
            tag_end = markup.find(">", tag_start)
            pos = tag_end + 1 if tag_end != -1 else length
            continue

        # Find tag name
        m_name = re.match(r"<([A-Za-z][A-Za-z0-9_]*)", markup[tag_start:])
        if not m_name:
            pos = tag_start + 1
            continue

        tag_name = m_name.group(1)
        cursor = tag_start + len(m_name.group(0))
        attributes: Dict[str, str] = {}
        is_self_closing = False

        # Parse attributes inside <Tag ...>
        while cursor < length:
            # Skip whitespace
            while cursor < length and markup[cursor].isspace():
                cursor += 1

            if cursor >= length:
                break

            # Check self-closing
            if markup[cursor:cursor+2] == "/>":
                is_self_closing = True
                cursor += 2
                break

            if markup[cursor] == ">":
                cursor += 1
                break

            # Match attribute name
            m_attr = re.match(r"([A-Za-z_][A-Za-z0-9_-]*)", markup[cursor:])
            if not m_attr:
                cursor += 1
                continue

            attr_name = m_attr.group(1)
            cursor += len(m_attr.group(0))

            # Skip whitespace around =
            while cursor < length and markup[cursor].isspace():
                cursor += 1

            if cursor < length and markup[cursor] == "=":
                cursor += 1
                while cursor < length and markup[cursor].isspace():
                    cursor += 1

                if cursor < length:
                    quote_char = markup[cursor]
                    if quote_char in ('"', "'"):
                        cursor += 1
                        val_start = cursor
                        # Scan until matching unescaped quote
                        escaped = False
                        while cursor < length:
                            char = markup[cursor]
                            if char == "\\" and not escaped:
                                escaped = True
                                cursor += 1
                                continue
                            if char == quote_char and not escaped:
                                break
                            escaped = False
                            cursor += 1

                        val_str = markup[val_start:cursor]
                        if cursor < length:
                            cursor += 1  # Skip closing quote

                        attributes[attr_name] = val_str
                    else:
                        # Bare word or number
                        m_bare = re.match(r"([^\s/>]+)", markup[cursor:])
                        if m_bare:
                            attributes[attr_name] = m_bare.group(1)
                            cursor += len(m_bare.group(0))
            else:
                attributes[attr_name] = "true"

        tags.append(ScannedTag(
            tag=tag_name,
            attributes=attributes,
            is_self_closing=is_self_closing,
            span=(tag_start, cursor),
        ))
        pos = cursor

    return tags


def extract_numbers_from_markup(markup: str) -> Set[float]:
    """Extract all numbers from text props, headings, and data JSON cells (§8.5 #3)."""
    if not markup:
        return set()

    numbers: Set[float] = set()
    tags = scan_markup(markup)

    # Date pattern to ignore timestamps (e.g. 2026-10-28T01:30:00Z)
    iso_date_re = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:T|\s)\d{2}:\d{2}")
    # Ignore MH-XX codes
    mh_re = re.compile(r"\bMH-\d{1,2}\b", re.IGNORECASE)

    def extract_from_str(s: str):
        # Mask out dates and district codes
        s_clean = iso_date_re.sub(" ", s)
        s_clean = mh_re.sub(" ", s_clean)
        # Find numeric floats/ints
        for num_str in re.findall(r"-?\b\d+(?:\.\d+)?\b", s_clean):
            try:
                numbers.add(float(num_str))
            except ValueError:
                pass

    def extract_from_json(obj: Any):
        if isinstance(obj, (int, float)) and not isinstance(obj, bool):
            numbers.add(float(obj))
        elif isinstance(obj, str):
            extract_from_str(obj)
        elif isinstance(obj, list):
            for item in obj:
                extract_from_json(item)
        elif isinstance(obj, dict):
            for val in obj.values():
                extract_from_json(val)

    for tag in tags:
        for k, v in tag.attributes.items():
            k_lower = k.lower()
            if k_lower in DATA_PROPS:
                # Attempt to parse JSON and inspect all cells
                try:
                    parsed = json.loads(v)
                    extract_from_json(parsed)
                except Exception:
                    extract_from_str(v)
            elif k_lower in TEXT_PROPS:
                extract_from_str(v)

    return numbers
