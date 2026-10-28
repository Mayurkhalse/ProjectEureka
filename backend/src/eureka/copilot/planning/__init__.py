"""Deterministic Query Planning and Entity Resolution for Nirdeshak Copilot."""

from eureka.copilot.planning.normalize import normalize_text, fold_devanagari, tokenize
from eureka.copilot.planning.gazetteer import resolve_entities, EntityMatch, EntityKind
from eureka.copilot.planning.lexicon import extract_topics, TopicMatch
from eureka.copilot.planning.ontology import expand_topics_to_ops
from eureka.copilot.planning.plan import Op, Plan, ParsedQuery
from eureka.copilot.planning.parser import parse_query

__all__ = [
    "normalize_text",
    "fold_devanagari",
    "tokenize",
    "resolve_entities",
    "EntityMatch",
    "EntityKind",
    "extract_topics",
    "TopicMatch",
    "expand_topics_to_ops",
    "Op",
    "Plan",
    "ParsedQuery",
    "parse_query",
]
