"""Domain Ontology: Topic expansion into typed candidate operations.

Expands high-level topics (e.g. 'crisis') into composite concrete tool operations
(e.g. active rumors + crisis SLA pillar breakdown). Binds operations distributively across entities.
"""

import re
from typing import List, Tuple

from eureka.copilot.policy.matrix import Intent
from eureka.copilot.planning.gazetteer import EntityMatch, EntityKind
from eureka.copilot.planning.plan import Op
from eureka.copilot.planning.lexicon import extract_topics

CLAUSE_DELIMITERS = re.compile(
    r'\b(?:and|also|while|whereas|as well as)\b|(?<![\u0900-\u097F])(?:तसेच|आणि|व|पण|परंतु|तथापि|और|तथा|एवं|जबकि)(?![\u0900-\u097F])|[,;\n+]',
    re.IGNORECASE
)


def _generate_ops_for_district_topic(
    d_code: str,
    d_name: str,
    defaulted: bool,
    topic: str,
    query: str,
    op_counter: int,
) -> Tuple[List[Op], int]:
    """Generate typed Op(s) for a specific district and topic combination."""
    ops: List[Op] = []
    if topic == "crisis":
        # Crisis expands to: rumors + crisis_sla pillar breakdown (§6.5)
        op_id1 = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id1,
            intent=Intent.RUMORS,
            tool="active_rumors",
            args={"district_code": d_code},
            districts=(d_code,),
            group=f"{d_code}:crisis",
            label=f"{d_name} · Crisis",
            defaulted_scope=defaulted,
            source="parser",
        ))
        op_id2 = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id2,
            intent=Intent.PILLAR,
            tool="pillar_breakdown",
            args={"district_code": d_code, "pillar_name": "crisis_sla"},
            districts=(d_code,),
            group=f"{d_code}:crisis",
            label=f"{d_name} · Crisis",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "sentiment":
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.PILLAR,
            tool="pillar_breakdown",
            args={"district_code": d_code, "pillar_name": "sentiment"},
            districts=(d_code,),
            group=f"{d_code}:sentiment",
            label=f"{d_name} · Sentiment",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "volume":
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.PILLAR,
            tool="pillar_breakdown",
            args={"district_code": d_code, "pillar_name": "volume"},
            districts=(d_code,),
            group=f"{d_code}:volume",
            label=f"{d_name} · Volume",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "rumors":
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.RUMORS,
            tool="active_rumors",
            args={"district_code": d_code},
            districts=(d_code,),
            group=f"{d_code}:rumors",
            label=f"{d_name} · Rumors",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "trend":
        days = _extract_trend_days(query)
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.TREND,
            tool="trend",
            args={"district_code": d_code, "metric": "composite_index", "days": days},
            districts=(d_code,),
            group=f"{d_code}:trend",
            label=f"{d_name} · Trend",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "forecast":
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.FORECAST,
            tool="forecast",
            args={"district_code": d_code},
            districts=(d_code,),
            group=f"{d_code}:forecast",
            label=f"{d_name} · Forecast",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "neighbors":
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.NEIGHBORS,
            tool="neighbors",
            args={"district_code": d_code, "max_hops": 1},
            districts=(d_code,),
            group=f"{d_code}:neighbors",
            label=f"{d_name} · Neighbors",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "dossier":
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.DOSSIER,
            tool="dossier_summary",
            args={"district_code": d_code},
            districts=(d_code,),
            group=f"{d_code}:dossier",
            label=f"{d_name} · Dossier",
            defaulted_scope=defaulted,
            source="parser",
        ))
    elif topic == "profile":
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.PROFILE,
            tool="district_profile",
            args={"district_code": d_code},
            districts=(d_code,),
            group=f"{d_code}:profile",
            label=f"{d_name} · Profile",
            defaulted_scope=defaulted,
            source="parser",
        ))
    return ops, op_counter



def _extract_trend_days(query: str) -> int:
    """Extract trend duration in days, clamped to 1..90 (default 30)."""
    q_lower = query.lower()
    if "week" in q_lower or "आठवडा" in query or "हफ्ता" in query:
        return 7
    if "month" in q_lower or "महिना" in query:
        return 30

    m = re.search(r"(\d{1,3})\s*(?:days?|दिवस|दिन)", query, re.IGNORECASE)
    if m:
        val = int(m.group(1))
        return max(1, min(90, val))
    return 30


def _extract_league_view(query: str) -> str:
    """Extract preferred visual representation for league table."""
    q_lower = query.lower()
    if "donut" in q_lower or "डोनट" in query:
        return "donut"
    if "pie" in q_lower or "पाय" in query or "वर्तुळ" in query:
        return "pie"
    if "table" in q_lower or "तक्ता" in query or "सारणी" in query:
        return "table"
    return "bar"


def expand_topics_to_ops(
    topics: List[str],
    entities: List[EntityMatch],
    query: str,
    default_district: str | None = None,
) -> Tuple[List[Op], List[str]]:
    """Expand matched topics and resolved entities into candidate operations.

    Returns:
      (operations: List[Op], clarifications: List[str])
    """
    ops: List[Op] = []
    clarifications: List[str] = []
    op_counter = 1

    district_entities = [e for e in entities if e.kind in (EntityKind.DISTRICT, EntityKind.POSSESSIVE)]
    division_entities = [e for e in entities if e.kind == EntityKind.DIVISION]

    # 1. Division Rollup: Triggered when a division entity is present
    if division_entities:
        for div_ent in division_entities:
            op_id = f"o{op_counter}"
            op_counter += 1
            ops.append(Op(
                op_id=op_id,
                intent=Intent.DIVISION_ROLLUP,
                tool="division_rollup",
                args={"division_code": div_ent.code},
                districts=(),
                group=f"{div_ent.code}:division_rollup",
                label=f"{div_ent.name_en} · Division Rollup",
                defaulted_scope=div_ent.defaulted_scope,
                source="parser",
            ))
        # If user only asked for division rollup, return early
        if not district_entities and not any(t in ("compare", "league") for t in topics):
            return ops, clarifications

    # 2. Compare Topic: Consumes all district entities together
    if "compare" in topics:
        if len(district_entities) >= 2:
            dist_codes = tuple(e.code for e in district_entities[:5])
            names = " vs ".join(e.name_en for e in district_entities[:5])
            op_id = f"o{op_counter}"
            op_counter += 1
            ops.append(Op(
                op_id=op_id,
                intent=Intent.COMPARE,
                tool="compare_districts",
                args={"district_codes": list(dist_codes)},
                districts=dist_codes,
                group="compare:districts",
                label=f"Compare · {names}",
                defaulted_scope=any(e.defaulted_scope for e in district_entities),
                source="parser",
            ))
        else:
            clarifications.append("compare_needs_two_districts")

    # 3. League Table: Statewide/Division ranking
    # Only trigger statewide league table if:
    # A) "league" is matched AND (no districts are specified OR query explicitly requests statewide leaderboard / table)
    # B) Or query explicitly requests statewide leaderboard / table via keywords (no districts and no divisions)
    explicit_statewide_keywords = [
        "leaderboard", "league table", "league", "तालिका", "सारणी", "लीडरबोर्ड", "लीडर बोर्ड",
        "all districts", "across districts", "सर्व जिल्हे", "सभी जिले",
        "statewide", "पूर्ण राज्य", "पूरे राज्य", "संपूर्ण महाराष्ट्र", "सर्वोत्तम", "सर्वश्रेष्ठ"
    ]
    q_lower = query.lower()
    has_explicit_statewide = any(kw in q_lower for kw in explicit_statewide_keywords)

    if ("league" in topics and (not district_entities or has_explicit_statewide)) or (has_explicit_statewide and not district_entities and not division_entities):
        view = _extract_league_view(query)
        op_id = f"o{op_counter}"
        op_counter += 1
        ops.append(Op(
            op_id=op_id,
            intent=Intent.LEAGUE,
            tool="league_table",
            args={"view": view},
            districts=(),
            group="statewide:league",
            label="Maharashtra · League Table",
            defaulted_scope=False,
            source="parser",
        ))

    # Determine target districts for distributive topics
    target_districts: List[Tuple[str, str, bool]] = []
    if district_entities:
        target_districts = [(e.code, e.name_en, e.defaulted_scope) for e in district_entities]
    elif default_district and any(t not in ("league", "compare") for t in topics):
        target_districts = [(default_district, "Your District", True)]

    # 4. Distributive Topics (Each entity x Each non-compare topic)
    distributive_topics = [t for t in topics if t not in ("compare", "league")]

    # If districts were named but no topic matched, default to generic profile
    if target_districts and not distributive_topics and "compare" not in topics:
        distributive_topics = ["profile"]

    # Check for disjoint multi-intent queries (e.g. "Crisis sla of Nashik and Sentiment score of Dhule")
    # Where distinct clauses each bind their own district(s) and topic(s).
    paired_clauses: List[Tuple[List[Tuple[str, str, bool]], List[str]]] = []
    if len(district_entities) >= 2 and "compare" not in topics:
        clause_spans = []
        last_idx = 0
        for m in CLAUSE_DELIMITERS.finditer(query):
            clause_spans.append((last_idx, m.start()))
            last_idx = m.end()
        clause_spans.append((last_idx, len(query)))

        topic_matches = extract_topics(query)
        for c_start, c_end in clause_spans:
            c_ents = [
                (e.code, e.name_en, e.defaulted_scope)
                for e in district_entities
                if e.span[0] >= c_start and e.span[1] <= c_end
            ]
            c_tops = [
                tm.topic
                for tm in topic_matches
                if tm.span[0] >= c_start and tm.span[1] <= c_end and tm.topic not in ("compare", "league")
            ]
            if c_ents and c_tops:
                paired_clauses.append((c_ents, c_tops))

    is_disjoint = (
        len(paired_clauses) >= 2
        and len({d[0] for c_ents, _ in paired_clauses for d in c_ents}) >= 2
    )

    if is_disjoint:
        for c_districts, c_topics in paired_clauses:
            for d_code, d_name, defaulted in c_districts:
                for topic in c_topics:
                    sub_ops, op_counter = _generate_ops_for_district_topic(
                        d_code=d_code,
                        d_name=d_name,
                        defaulted=defaulted,
                        topic=topic,
                        query=query,
                        op_counter=op_counter,
                    )
                    ops.extend(sub_ops)
    else:
        for d_code, d_name, defaulted in target_districts:
            for topic in distributive_topics:
                sub_ops, op_counter = _generate_ops_for_district_topic(
                    d_code=d_code,
                    d_name=d_name,
                    defaulted=defaulted,
                    topic=topic,
                    query=query,
                    op_counter=op_counter,
                )
                ops.extend(sub_ops)

    def _freeze(val):
        if isinstance(val, dict):
            return tuple(sorted((k, _freeze(v)) for k, v in val.items()))
        elif isinstance(val, (list, tuple)):
            return tuple(_freeze(v) for v in val)
        return val

    # Deduplicate identical (tool, args) pairs while preserving order
    deduped_ops: List[Op] = []
    seen_ops = set()
    for o in ops:
        key = (o.tool, _freeze(o.args))
        if key not in seen_ops:
            deduped_ops.append(o)
            seen_ops.add(key)

    if not deduped_ops and not clarifications:
        clarifications.append("unrecognized_query")

    return deduped_ops, clarifications
