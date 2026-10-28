"""Pure Deterministic Query Parser.

Transforms untrusted user query text into a structured ParsedQuery containing
typed candidate operations (Ops), confidence score, and residual tokens.
Zero side-effects: makes NO tool, database, or LLM calls.
"""

from typing import List, Optional

from eureka.copilot.policy.principal import PolicyPrincipal
from eureka.copilot.planning.normalize import normalize_text, tokenize
from eureka.copilot.planning.gazetteer import resolve_entities
from eureka.copilot.planning.lexicon import extract_topics, STOPWORDS
from eureka.copilot.planning.ontology import expand_topics_to_ops
from eureka.copilot.planning.plan import ParsedQuery


def parse_query(
    query: str,
    principal: Optional[PolicyPrincipal] = None,
) -> ParsedQuery:
    """Deterministically parse query into typed operations, confidence, and residuals."""
    if not query or not query.strip():
        return ParsedQuery(
            ops=(),
            confidence=0.0,
            residual_tokens=(),
            clarifications=("empty_query",),
        )

    norm_query = normalize_text(query)
    all_tokens = tokenize(norm_query)

    # 1. Resolve district and division entities
    entities = resolve_entities(query, principal=principal)

    # 2. Extract domain topics
    topic_matches = extract_topics(query)
    topic_names = [tm.topic for tm in topic_matches]

    # 3. Expand topics and entities into concrete candidate operations
    default_dist = principal.district_code if principal else None
    ops, clarifications = expand_topics_to_ops(
        topics=topic_names,
        entities=entities,
        query=query,
        default_district=default_dist,
    )

    # 4. Track explained tokens for coverage & confidence computation (§6.6)
    explained_tokens: set[str] = set()

    # Explained by entities
    for ent in entities:
        for t in tokenize(normalize_text(ent.raw_text)):
            explained_tokens.add(t)

    # Explained by topic triggers
    for tm in topic_matches:
        for t in tokenize(normalize_text(tm.trigger)):
            explained_tokens.add(t)

    # Explained by stopwords and numbers
    for t in all_tokens:
        if t in STOPWORDS or t.isdigit():
            explained_tokens.add(t)

    residual_tokens: List[str] = [t for t in all_tokens if t not in explained_tokens]

    # Compute coverage ratio
    total_token_chars = sum(len(t) for t in all_tokens)
    explained_chars = sum(len(t) for t in all_tokens if t in explained_tokens)

    if total_token_chars > 0:
        coverage = min(1.0, explained_chars / total_token_chars)
    else:
        coverage = 0.0

    # Confidence calculation per §6.6
    confidence = coverage
    if not ops:
        confidence = min(0.5, confidence)
    if clarifications:
        confidence = max(0.0, confidence - 0.2 * len(clarifications))

    return ParsedQuery(
        ops=tuple(ops),
        confidence=round(confidence, 2),
        residual_tokens=tuple(residual_tokens),
        clarifications=tuple(clarifications),
    )
