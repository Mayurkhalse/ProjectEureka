"""Response Composer: Transforms OpResults and Decisions into Ordered Sections.

Produces validated, ordered OpenUI Lang sections:
  Order 0: Executive summary (narrator, optional)
  Order 10+n: Content groups in query order (with data-quality warnings if non-live)
  Order 900: Deterministic notices (denials, missing sources, clarifications)
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

from eureka.copilot.execution.results import OpResult
from eureka.copilot.policy.decisions import Decision, Reason
from eureka.copilot.response.prefs import PresentationPrefs
from eureka.copilot.response.notices import get_notice
from eureka.copilot.viewspec import ViewSpecBuilder, sanitize_markup_for_frontend

logger = logging.getLogger("eureka.copilot.response.composer")


@dataclass(frozen=True)
class Section:
    """An individual chunk of OpenUI markup with deterministic ordering."""
    section_id: str
    order: int
    markup: str
    provenance: Literal["deterministic", "narrator", "notice"]
    data_quality: str = "live"


def compose(
    results: List[OpResult],
    denied: List[Decision],
    prefs: Optional[PresentationPrefs] = None,
    language: str = "en",
    narrator_summaries: Optional[Dict[str, str]] = None,
    clarifications: Optional[List[str]] = None,
) -> List[Section]:
    """Compose ordered OpenUI Lang sections from execution results and decisions."""
    sections: List[Section] = []
    lang = language if language in ("mr", "hi", "en") else "en"
    narrator_summaries = narrator_summaries or {}
    clarifications = clarifications or []

    # 1. Narrator prose summary (Order 0, if available)
    if narrator_summaries:
        summary_lines = []
        for sec_id, prose in narrator_summaries.items():
            summary_lines.append(f'<Text content="{prose}" />')
        if summary_lines:
            summary_markup = '<Heading level="3" text="Executive Briefing" />\n' + "\n".join(summary_lines)
            sections.append(Section(
                section_id="summary",
                order=0,
                markup=summary_markup,
                provenance="narrator",
                data_quality="live",
            ))

    # 2. Grouped OpResults (Order 10 + n)
    # Group results by group ID
    grouped_results: Dict[str, List[OpResult]] = {}
    for res in results:
        grp = res.group or res.op_id
        if grp not in grouped_results:
            grouped_results[grp] = []
        grouped_results[grp].append(res)

    order_idx = 10
    for group_id, grp_results in grouped_results.items():
        markup_parts: List[str] = []

        # Find group label
        first_res = grp_results[0]
        group_label = f"{first_res.tool.replace('_', ' ').title()}"
        if "district_code" in first_res.args:
            from eureka.copilot.planning.gazetteer import get_district_name
            d_name = get_district_name(first_res.args['district_code'])
            group_label = f"{d_name} · {group_label}"

        markup_parts.append(f'<Heading level="3" text="{group_label}" />')

        # Check data quality for warning banner (§7.4, §8.1)
        worst_quality = "live"
        quality_priority = {"seed": 4, "synthetic": 3, "heuristic": 2, "pipeline_memory": 1, "partial": 1, "live": 0}
        for res in grp_results:
            if quality_priority.get(res.data_quality, 0) > quality_priority.get(worst_quality, 0):
                worst_quality = res.data_quality

        if worst_quality not in ("live", "pipeline_memory"):
            banner_text = get_notice(worst_quality, lang=lang)
            if banner_text:
                markup_parts.append(f'<Callout type="warning" message="{banner_text}" />')

        # Render ViewSpec for each op in group
        for res in grp_results:
            if res.status == "ok" and res.data:
                try:
                    view = ViewSpecBuilder.build_from_tool_result(res.tool, res.data, language=lang)
                    markup_parts.append(view.to_openui_lang())
                except Exception as exc:
                    logger.warning("composer.viewspec_error: %s", exc)
                    markup_parts.append(f'<Text content="Data summary unavailable for {res.tool}." />')
            elif res.status == "timeout":
                timeout_msg = get_notice("timeout", lang=lang, labels=res.tool)
                markup_parts.append(f'<Callout type="warning" message="{timeout_msg}" />')
            else:
                markup_parts.append(f'<Callout type="critical" message="Tool execution failed for {res.tool}." />')

        sections.append(Section(
            section_id=group_id,
            order=order_idx,
            markup=sanitize_markup_for_frontend("\n\n".join(markup_parts)),
            provenance="fast_path",
            data_quality=worst_quality,
        ))
        order_idx += 1

    # 3. Deterministic Notices (Order 900) for Denials & Clarifications
    notice_parts: List[str] = []

    # Handle Clarifications
    if clarifications:
        for c in clarifications:
            if c == "compare_needs_two_districts":
                msg = get_notice("clarify_compare", lang=lang)
                notice_parts.append(f'<Callout type="info" message="{msg}" />')
            elif c in ("empty_query", "unreadable", "unrecognized_query"):
                msg = get_notice("unrecognized_query" if c == "unrecognized_query" else "unreadable", lang=lang)
                notice_parts.append(f'<Callout type="info" message="{msg}" />')

    # If absolutely no results, no denials, and no specific notices, provide an unrecognized query guidance callout
    if not results and not denied and not notice_parts:
        msg = get_notice("unrecognized_query", lang=lang)
        notice_parts.append(f'<Callout type="info" message="{msg}" />')

    # Handle Denials (Uniform wording per D5; never discloses internal reasons to caller)
    access_denied_labels = []
    source_missing_labels = []

    for d in denied:
        if d.reason == Reason.SOURCE_NOT_AVAILABLE:
            source_missing_labels.append(d.op_id)
        elif d.reason != Reason.LIMIT_EXCEEDED:
            access_denied_labels.append(d.op_id)

    if access_denied_labels:
        msg = get_notice("unavailable", lang=lang, labels=", ".join(access_denied_labels))
        notice_parts.append(f'<Callout type="info" message="{msg}" />')

    if source_missing_labels:
        msg = get_notice("source_missing", lang=lang, labels=", ".join(source_missing_labels))
        notice_parts.append(f'<Callout type="warning" message="{msg}" />')

    if notice_parts:
        sections.append(Section(
            section_id="notices",
            order=900,
            markup=sanitize_markup_for_frontend("\n\n".join(notice_parts)),
            provenance="notice",
            data_quality="live",
        ))

    return sections
