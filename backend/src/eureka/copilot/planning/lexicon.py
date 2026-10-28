"""Multilingual Lexicon and Intent Triggers for Nirdeshak Copilot.

Identifies domain topics across English, Marathi, Hindi, and Romanized text.
Enforces rules:
  1. Conjunctions ('and', 'आणि', 'और') are NEVER compare triggers.
  2. Generic 'profile' is suppressed when any specific topic is matched.
  3. Whole token / phrase boundary matching only (no substring false-positives).
"""

import re
from dataclasses import dataclass
from typing import List, Set, Tuple

from eureka.copilot.planning.normalize import normalize_text


@dataclass(frozen=True)
class TopicMatch:
    topic: str
    trigger: str
    span: Tuple[int, int]


TOPIC_TRIGGERS: dict[str, List[str]] = {
    "crisis": [
        "crisis sla", "crisis", "emergency", "disaster", "sla",
        "crisiss", "crises", "crisi", "crizis", "क्राइसिस",
        "संकट", "आपत्ती", "आपत्कालीन", "आपतकालीन", "आपातकाल",
        "sankat", "aapatti",
    ],
    "sentiment": [
        "public mood", "people think", "public opinion", "sentiment", "mood", "opinion",
        "sentimnt", "sentimant", "sentment", "सेंटिमेंट", "सेंटीमेंट", "सेन्टिमेंट", "सेन्टीमेंट",
        "भावना", "जनभावना", "जनमत", "विचार", "bhavna",
    ],
    "volume": [
        "news count", "volume", "releases", "coverage", "press releases",
        "releeses", "volum",
        "प्रसिद्धी", "बातम्यांची संख्या", "प्रसिद्धि", "समाचार संख्या",
    ],
    "rumors": [
        "fake news", "fact check", "fact-check", "rumor", "rumour", "rumors", "rumours",
        "romors", "rumers", "fakenews",
        "अफवा", "खोट्या बातम्या", "फॅक्ट चेक", "तथ्य तपासणी", "अफ़वाह", "अफवाह", "अफवाहें", "afwa",
    ],
    "trend": [
        "over time", "last 30 days", "last 7 days", "trend", "trends", "history", "trnd",
        "कल", "ट्रेंड", "रुझान",
    ],
    "forecast": [
        "forecast", "predict", "prediction", "diffusion", "spread", "outlook", "stgnn",
        "अंदाज", "भविष्यवाणी", "पूर्वानुमान", "प्रसार",
    ],
    "neighbors": [
        "neighbouring", "neighboring", "neighbors", "neighbours", "neighbor", "neighbour",
        "adjacent", "border", "borders", "शेजारी", "शेजारील", "शेजारील जिल्हे", "सीमा", "पड़ोसी",
    ],
    "compare": [
        "comparison", "compare", "versus", " vs ", "against", "compr", "comapre", "compair", "कम्पेयर",
        "तुलना करा", "तुलना", "मुकाबला",
    ],
    "league": [
        "leaderboard", "league table", "league", "rankings", "ranking",
        "leadrboard", "leadreboard", "rankng",
        "rank 1", "top 1", "number 1", "no 1", "first rank", "top ranked",
        "top 5", "top 10", "top 3", "top districts", "top performers",
        "bottom 5", "bottom 10", "bottom 3", "bottom districts", "lowest ranked", "highest ranked",
        "क्रमवारी", "रँकिंग", "सर्वोत्तम", "रैंकिंग", "सर्वश्रेष्ठ", "तालिका", "क्रमांक १", "पहिला क्रमांक", "लीडरबोर्ड", "लीडर बोर्ड",
    ],
    "dossier": [
        "full report", "dossier", "briefing",
        "सविस्तर अहवाल", "विस्तृत रिपोर्ट",
    ],
    "profile": [
        "overview", "analysis", "summary", "profile", "performance", "details",
        "standing", "position", "rank", "status", "situation", "how is", "doing",
        "माहिती", "कामगिरी", "विश्लेषण", "जानकारी", "प्रदर्शन", "तपशील",
        "स्थान", "रँक", "रैंक", "हालत", "स्थिति", "परिस्थिती",
    ],
}

STOPWORDS: Set[str] = {
    "a", "an", "the", "of", "in", "for", "and", "or", "to", "show", "me",
    "give", "tell", "what", "is", "are", "about", "please", "all",
    "why", "how", "explain", "explanation", "reason", "reasons", "it",
    "at", "this", "that", "these", "those", "should", "too", "so", "very",
    "low", "high", "good", "bad", "score", "status", "data", "available",
    "आणि", "व", "किंवा", "दाखवा", "द्या", "करा", "काय", "आहे", "का",
    "च्या", "ची", "चे", "चा", "मध्ये", "तील", "वरून", "बदल", "बद्दल",
    "कसे", "कशी", "कसा", "स्पष्ट", "कारण", "कमी", "जास्त", "फार", "खूप",
    "हे", "ते", "या", "त्या", "काही", "होते", "आहेत", "सांगा", "सांगावे",
    "और", "तथा", "दिखाएं", "बताएं", "का", "के", "की", "में", "से",
    "क्यों", "कैसे", "कम", "ज्यादा", "बताओ", "समझाओ", "कारण", "यह", "वह", "इस", "उस",
}


def extract_topics(query: str) -> List[TopicMatch]:
    """Extract all distinct domain topics present in the query."""
    if not query:
        return []

    norm_query = normalize_text(query)
    matches: List[TopicMatch] = []
    matched_topics: Set[str] = set()

    # Search each topic's triggers
    for topic, triggers in TOPIC_TRIGGERS.items():
        # Sort triggers by length descending
        sorted_triggers = sorted(triggers, key=len, reverse=True)
        for trigger in sorted_triggers:
            norm_trigger = normalize_text(trigger)
            pattern = r"(?:^|\s|\b)" + re.escape(norm_trigger) + r"(?:\b|\s|$)"
            m = re.search(pattern, norm_query)
            if m:
                # Calculate span in normalized query
                span_start = m.start()
                span_end = m.end()
                matches.append(TopicMatch(
                    topic=topic,
                    trigger=trigger,
                    span=(span_start, span_end),
                ))
                matched_topics.add(topic)
                break  # Matched this topic, move to next topic

    # Rule: Suppress generic 'profile' whenever a specific topic is matched
    specific_topics = matched_topics - {"profile"}
    if specific_topics:
        matches = [m for m in matches if m.topic != "profile"]

    return matches
