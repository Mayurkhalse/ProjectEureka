"""Deterministic ViewSpec Schema & Canonical Builder.

Serves as:
1. Ground truth representation of governed tool data.
2. Guaranteed fallback when generative OpenUI output fails validation or repair.
3. Fully compliant with GIGW 3.0 & UX4G accessibility (every chart/graph includes text summary and table alternative).
"""

import re
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class BaseComponentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: str


class TextSpec(BaseComponentSpec):
    component: Literal["Text"] = "Text"
    content: str


class HeadingSpec(BaseComponentSpec):
    component: Literal["Heading"] = "Heading"
    level: int = Field(default=2, ge=1, le=4)
    text: str


class CalloutSpec(BaseComponentSpec):
    component: Literal["Callout"] = "Callout"
    type: Literal["info", "warning", "success", "critical"] = "info"
    message: str


class KpiCardSpec(BaseComponentSpec):
    component: Literal["KpiCard"] = "KpiCard"
    title: str
    value: Union[str, float, int]
    unit: Optional[str] = None
    delta: Optional[float] = None
    status: Literal["positive", "negative", "neutral", "critical"] = "neutral"
    caption: Optional[str] = None


class DataTableSpec(BaseComponentSpec):
    component: Literal["DataTable"] = "DataTable"
    columns: List[str]
    rows: List[Dict[str, Any]]
    caption: Optional[str] = None


class BarChartSpec(BaseComponentSpec):
    component: Literal["BarChart"] = "BarChart"
    title: str
    x_key: str
    y_key: str
    data: List[Dict[str, Any]]
    text_summary: str = Field(description="Accessible summary for screen readers & GIGW 3.0")
    table_alternative: DataTableSpec


class LineChartSpec(BaseComponentSpec):
    component: Literal["LineChart"] = "LineChart"
    title: str
    x_key: str
    y_key: str
    data: List[Dict[str, Any]]
    text_summary: str = Field(description="Accessible summary for screen readers & GIGW 3.0")
    table_alternative: DataTableSpec


class PieChartSpec(BaseComponentSpec):
    component: Literal["PieChart"] = "PieChart"
    title: str
    categories: Optional[List[str]] = None
    values: Optional[List[Union[int, float]]] = None
    variant: Literal["pie", "donut"] = "donut"
    data: Optional[List[Dict[str, Any]]] = None
    text_summary: str = Field(description="Accessible summary for screen readers & GIGW 3.0")
    table_alternative: DataTableSpec


class GraphViewSpec(BaseComponentSpec):
    component: Literal["GraphView"] = "GraphView"
    title: str
    nodes: List[Dict[str, Any]] = Field(max_length=200, description="Capped at 200 nodes for performance")
    edges: List[Dict[str, Any]]
    text_summary: str
    table_alternative: DataTableSpec


class StackSpec(BaseComponentSpec):
    component: Literal["Stack"] = "Stack"
    direction: Literal["vertical", "horizontal"] = "vertical"
    children: List[Union[
        KpiCardSpec,
        DataTableSpec,
        BarChartSpec,
        LineChartSpec,
        PieChartSpec,
        GraphViewSpec,
        CalloutSpec,
        HeadingSpec,
        TextSpec,
    ]]


AnyComponentSpec = Union[
    StackSpec,
    KpiCardSpec,
    DataTableSpec,
    BarChartSpec,
    LineChartSpec,
    PieChartSpec,
    GraphViewSpec,
    CalloutSpec,
    HeadingSpec,
    TextSpec,
]


class ViewSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    as_of: str
    source_status: Literal["live", "demo", "unavailable"] = "live"
    district_code: Optional[str] = None
    fallback: bool = False
    components: List[AnyComponentSpec]

    def to_openui_lang(self) -> str:
        """Render the ViewSpec into valid OpenUI Lang syntax for streaming/rendering."""
        lines = []
        for comp in self.components:
            rendered = render_component_to_openui(comp)
            if rendered:
                lines.append(rendered)
        raw_markup = "\n\n".join(lines)
        return sanitize_markup_for_frontend(raw_markup)


def sanitize_markup_for_frontend(markup: str) -> str:
    """Sanitize OpenUI markup for frontend CopilotDrawer parser:
    1. Unwraps <Stack> tags so child components render at top level without raw <Stack> code blocks.
    2. Converts raw markdown headings (e.g. ## Heading) into <Heading level=... text=... /> tags.
    """
    if not markup:
        return ""
    # 1. Unwrap <Stack ...> and </Stack>
    clean = re.sub(r'<\s*Stack\b[^>]*>', '', markup)
    clean = re.sub(r'<\s*/\s*Stack\s*>', '', clean)

    # 2. Convert markdown headers if present
    def _header_sub(m):
        hashes = m.group(1)
        title = m.group(2).strip().replace('"', '&quot;')
        level = len(hashes)
        return f'<Heading level="{level}" text="{title}" />'

    clean = re.sub(r'^(#{1,4})\s+(.+)$', _header_sub, clean, flags=re.MULTILINE)
    return clean.strip()


def render_component_to_openui(comp: AnyComponentSpec) -> str:
    """Recursively convert a typed component specification into OpenUI Lang markup."""
    c_type = comp.component

    if c_type == "Heading":
        h = comp  # type: HeadingSpec
        safe_text = h.text.replace('"', '&quot;')
        return f'<Heading level="{h.level}" text="{safe_text}" />'

    if c_type == "Text":
        t = comp  # type: TextSpec
        safe_content = t.content.replace('"', '&quot;')
        return f'<Text content="{safe_content}" />'

    if c_type == "Callout":
        c = comp  # type: CalloutSpec
        safe_msg = c.message.replace('"', '&quot;')
        return f'<Callout type="{c.type}" message="{safe_msg}" />'

    if c_type == "KpiCard":
        k = comp  # type: KpiCardSpec
        safe_title = k.title.replace('"', '&quot;')
        props = [f'title="{safe_title}"', f'value="{k.value}"']
        if k.unit:
            safe_unit = k.unit.replace('"', '&quot;')
            props.append(f'unit="{safe_unit}"')
        if k.delta is not None:
            props.append(f'delta={k.delta}')
        props.append(f'status="{k.status}"')
        if k.caption:
            safe_caption = k.caption.replace('"', '&quot;')
            props.append(f'caption="{safe_caption}"')
        return f"<KpiCard {' '.join(props)} />"

    if c_type == "DataTable":
        dt = comp  # type: DataTableSpec
        cols_str = ",".join(dt.columns)
        # Format rows simply
        rows_data = []
        for r in dt.rows[:50]:  # Cap rows for prompt brevity
            rows_data.append(r)
        import json
        rows_json = json.dumps(rows_data).replace('"', '&quot;')
        return f'<DataTable columns="{cols_str}" rows="{rows_json}" />'

    if c_type in ("BarChart", "LineChart"):
        chart = comp
        import json
        data_json = json.dumps(chart.data).replace('"', '&quot;')
        tbl_comp = render_component_to_openui(chart.table_alternative)
        return (
            f'<{c_type} title="{chart.title}" xKey="{chart.x_key}" yKey="{chart.y_key}" data="{data_json}">\n'
            f'  <Text content="{chart.text_summary}" />\n'
            f'  {tbl_comp}\n'
            f'</{c_type}>'
        )

    if c_type == "PieChart":
        pie = comp  # type: PieChartSpec
        import json
        data_json = json.dumps(pie.data or []).replace('"', '&quot;')
        cats_json = json.dumps(pie.categories or []).replace('"', '&quot;')
        vals_json = json.dumps(pie.values or []).replace('"', '&quot;')
        tbl_comp = render_component_to_openui(pie.table_alternative)
        return (
            f'<PieChart title="{pie.title}" variant="{pie.variant}" categories="{cats_json}" values="{vals_json}" data="{data_json}">\n'
            f'  <Text content="{pie.text_summary}" />\n'
            f'  {tbl_comp}\n'
            f'</PieChart>'
        )

    if c_type == "GraphView":
        gv = comp  # type: GraphViewSpec
        import json
        nodes_json = json.dumps(gv.nodes[:200]).replace('"', '&quot;')
        edges_json = json.dumps(gv.edges[:300]).replace('"', '&quot;')
        tbl_comp = render_component_to_openui(gv.table_alternative)
        return (
            f'<GraphView title="{gv.title}" nodes="{nodes_json}" edges="{edges_json}">\n'
            f'  <Text content="{gv.text_summary}" />\n'
            f'  {tbl_comp}\n'
            f'</GraphView>'
        )

    if c_type == "Stack":
        st = comp  # type: StackSpec
        rendered_children = [render_component_to_openui(child) for child in st.children]
        return "\n\n".join(r for r in rendered_children if r)

    return ""


class ViewSpecBuilder:
    """Builds authoritative, zero-hallucination ViewSpecs directly from governed tool data."""

    @staticmethod
    def build_from_tool_result(tool_name: str, tool_result: Dict[str, Any], fallback: bool = False, language: str = "en") -> ViewSpec:
        as_of = tool_result.get("as_of", "2026-10-19T00:00:00Z")
        status = tool_result.get("source_status", "live")
        data = tool_result.get("data", {})

        # Handle permission denied or errors
        if "error" in tool_result or (isinstance(data, dict) and "error" in data):
            err_msg = tool_result.get("message") or (data.get("message") if isinstance(data, dict) else "Access refused.")
            return ViewSpec(
                title="Access Restricted",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=[
                    CalloutSpec(type="critical", message=str(err_msg)),
                    TextSpec(content="You do not have administrative authorization to inspect this district or jurisdiction."),
                ],
            )

        if tool_name == "league_table":
            districts = data.get("districts", []) if isinstance(data, dict) else data
            top_kpis = []
            if districts:
                top_1 = districts[0]
                top_kpis.append(
                    KpiCardSpec(
                        title=f"Top Ranked: {top_1.get('name_en')}",
                        value=top_1.get("composite_index", 0.0),
                        unit="/100",
                        status="positive",
                        caption="Rank #1 Maharashtra",
                    )
                )
            
            table_rows = []
            chart_data = []
            for d in districts:
                table_rows.append({
                    "Rank": d.get("rank"),
                    "District": f"{d.get('name_en')} ({d.get('name_mr')})",
                    "Score": d.get("composite_index"),
                    "Volume": d.get("pillars", {}).get("volume", 0),
                    "Sentiment": d.get("pillars", {}).get("sentiment", 0),
                    "Crisis SLA": d.get("pillars", {}).get("crisis_sla", 0),
                })
                chart_data.append({
                    "district": d.get("name_en"),
                    "score": d.get("composite_index"),
                })

            table_spec = DataTableSpec(
                columns=["Rank", "District", "Score", "Volume", "Sentiment", "Crisis SLA"],
                rows=table_rows,
                caption="100-Point Composite Governance Index Leaderboard",
            )

            view_mode = tool_result.get("view") or (data.get("view") if isinstance(data, dict) else "bar")
            if view_mode in ("pie", "donut"):
                top_slice = districts[:6]
                chart_spec = PieChartSpec(
                    title="Leading Districts Share of Score",
                    categories=[d.get("name_en") for d in top_slice],
                    values=[d.get("composite_index") for d in top_slice],
                    variant="donut" if view_mode == "donut" else "pie",
                    data=[{"name": d.get("name_en"), "value": d.get("composite_index")} for d in top_slice],
                    text_summary=f"Distribution of composite index among leading {len(top_slice)} districts.",
                    table_alternative=table_spec,
                )
            else:
                chart_spec = BarChartSpec(
                    title="District Performance Comparison",
                    x_key="district",
                    y_key="score",
                    data=chart_data[:15],
                    text_summary=f"Leaderboard comparing {len(districts)} districts. Top rank is {districts[0].get('name_en') if districts else 'N/A'}.",
                    table_alternative=table_spec,
                )

            components: List[AnyComponentSpec] = [
                HeadingSpec(level=2, text="Maharashtra District Governance Leaderboard"),
            ]
            if top_kpis:
                components.append(top_kpis[0])
            components.extend([chart_spec, table_spec])

            return ViewSpec(
                title="District Governance Leaderboard",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=components,
            )

        if tool_name == "pillar_breakdown" and data.get("pillar"):
            d_name = data.get("name_en") or data.get("district_name") or "District"
            d_code = data.get("district_code", "MH-XX")
            p_key = str(data.get("pillar", "pillar")).lower().strip()
            p_score = float(data.get("score", 0.0))
            raw = data.get("raw_metrics", {})
            max_pts = 30 if p_key == "crisis_sla" else 35
            p_display = "Crisis SLA" if p_key == "crisis_sla" else p_key.replace("_", " ").title()

            components: List[AnyComponentSpec] = [
                HeadingSpec(level=2, text=f"{d_name} — {p_display} Analysis"),
            ]

            if p_key == "crisis_sla":
                act_rumors = raw.get("active_crisis_tickets", 0)
                if act_rumors > 0:
                    expl = (
                        f"Explanation: {d_name}'s Crisis SLA score is {p_score}/{max_pts} (critical) "
                        f"due to {act_rumors} active rumor ticket(s) currently awaiting verification within the 90-minute SLA window."
                    )
                else:
                    expl = f"Explanation: {d_name}'s Crisis SLA score is {p_score}/{max_pts} with all fact-check tickets resolved within SLA."

                components.append(CalloutSpec(type="critical" if act_rumors > 0 else "success", message=expl))
                components.append(StackSpec(direction="horizontal", children=[
                    KpiCardSpec(title="Crisis SLA Score", value=p_score, unit=f"/{max_pts}", status="critical" if p_score < 20 else "positive", caption="Pillar Assessment"),
                    KpiCardSpec(title="Active Crisis Rumors", value=act_rumors, status="critical" if act_rumors > 0 else "positive", caption="Direct SLA Penalty Factor"),
                ]))
                components.append(DataTableSpec(
                    columns=["Metric", "Value", "Benchmark", "Impact on Score"],
                    rows=[
                        {"Metric": "Active Crisis Rumors", "Value": str(act_rumors), "Benchmark": "0", "Impact on Score": f"-{(max_pts - p_score):.1f} pts (SLA queue penalty)" if act_rumors > 0 else "Full Score"},
                        {"Metric": "Official Releases", "Value": str(raw.get("total_releases", 0)), "Benchmark": "200+", "Impact on Score": "Information Volume factor"},
                        {"Metric": "Net Sentiment", "Value": f"{raw.get('net_sentiment', 0):.2f}", "Benchmark": "0.60+", "Impact on Score": "Public mood factor"},
                    ],
                    caption=f"Crisis SLA Factor Decomposition for {d_name} ({d_code})",
                ))
            else:
                components.append(CalloutSpec(type="info", message=f"{d_name}'s {p_display} score is {p_score}/{max_pts} based on governed media telemetry."))
                components.append(KpiCardSpec(title=f"{p_display} Score", value=p_score, unit=f"/{max_pts}", status="positive" if p_score >= 25 else "neutral"))

            return ViewSpec(
                title=f"{d_name} ({d_code}): {p_display}",
                as_of=as_of,
                source_status=status,
                district_code=d_code,
                fallback=fallback,
                components=components,
            )

        if tool_name in ("district_profile", "pillar_breakdown"):
            d_name = data.get("name_en") or data.get("district_name") or "District"
            d_code = data.get("district_code", "MH-XX")
            score = data.get("composite_index", 0.0)
            pillars = data.get("pillars", {})
            raw = data.get("raw_metrics", {})
            rank = data.get("rank")

            kpis = [
                KpiCardSpec(title="Composite Index", value=score, unit="/100", status="positive" if score >= 75 else "neutral"),
            ]
            if rank:
                kpis.append(KpiCardSpec(
                    title="Statewide Rank",
                    value=f"#{rank}",
                    unit="of 36",
                    status="negative" if rank > 25 else ("positive" if rank <= 10 else "neutral"),
                    caption="Maharashtra Ranking",
                ))
            kpis.extend([
                KpiCardSpec(title="Volume Pillar", value=pillars.get("volume", 0), unit="/35"),
                KpiCardSpec(title="Sentiment Pillar", value=pillars.get("sentiment", 0), unit="/35"),
                KpiCardSpec(title="Crisis SLA Pillar", value=pillars.get("crisis_sla", 0), unit="/30", status="critical" if raw.get("active_crisis_tickets", 0) > 0 else "positive"),
            ])

            pillar_rows = [
                {"Pillar": "Information Volume", "Score": pillars.get("volume", 0), "Max": 35, "Detail": f"{raw.get('total_releases', 0)} official releases"},
                {"Pillar": "Net Sentiment", "Score": pillars.get("sentiment", 0), "Max": 35, "Detail": f"{raw.get('net_sentiment', 0):.2f} NSI score"},
                {"Pillar": "Crisis SLA", "Score": pillars.get("crisis_sla", 0), "Max": 30, "Detail": f"{raw.get('active_crisis_tickets', 0)} active rumors"},
            ]

            table_spec = DataTableSpec(
                columns=["Pillar", "Score", "Max", "Detail"],
                rows=pillar_rows,
                caption=f"3-Pillar Breakdown for {d_name} ({d_code})",
            )

            components = [
                HeadingSpec(level=2, text=f"{d_name} ({data.get('name_mr', '')}) — Performance Dossier"),
            ]

            # Explanation of rank / score
            if rank:
                c_vol = pillars.get("volume", 0)
                c_sent = pillars.get("sentiment", 0)
                c_sla = pillars.get("crisis_sla", 0)
                act_rumors = raw.get("active_crisis_tickets", 0)

                if rank > 20:
                    contributors = []
                    if c_sla < 20:
                        contributors.append(f"Crisis SLA ({c_sla}/30 with {act_rumors} active rumor(s))")
                    if c_vol < 25:
                        contributors.append(f"Information Volume ({c_vol}/35 with {raw.get('total_releases', 0)} releases)")
                    if c_sent < 25:
                        contributors.append(f"Net Sentiment ({c_sent}/35 with {raw.get('net_sentiment', 0):.2f} NSI)")
                    contrib_str = " and ".join(contributors) if contributors else f"a Composite Index of {score}/100"

                    expl_callout = CalloutSpec(
                        type="info",
                        message=f"Rank Explanation: {d_name} is currently ranked #{rank} of 36 in Maharashtra with a Composite Index of {score}/100. Its standing is primarily impacted by {contrib_str}."
                    )
                else:
                    expl_callout = CalloutSpec(
                        type="info",
                        message=f"Rank Explanation: {d_name} is ranked #{rank} of 36 in Maharashtra with a Composite Index of {score}/100, reflecting strong overall media governance performance."
                    )
                components.append(expl_callout)

            components.extend([
                StackSpec(direction="horizontal", children=kpis[:3]),
                StackSpec(direction="horizontal", children=kpis[3:]),
                table_spec,
            ])

            return ViewSpec(
                title=f"District Profile: {d_name} ({d_code})",
                as_of=as_of,
                source_status=status,
                district_code=d_code,
                fallback=fallback,
                components=components,
            )

        if tool_name == "active_rumors":
            tickets = data.get("tickets", []) if isinstance(data, dict) else data
            rows = []
            for t in tickets:
                rows.append({
                    "Ticket ID": t.get("ticket_id"),
                    "Claim": t.get("claim_text", "")[:60],
                    "District": t.get("district_code"),
                    "SLA Remaining": t.get("sla_remaining_formatted", "N/A"),
                    "Urgency": t.get("urgency_level", "NORMAL"),
                })

            table_spec = DataTableSpec(
                columns=["Ticket ID", "Claim", "District", "SLA Remaining", "Urgency"],
                rows=rows,
                caption="Active Crisis & Rumor SLA Queue",
            )

            urgent_count = sum(1 for t in tickets if t.get("urgency_level") == "CRITICAL")
            callout = CalloutSpec(
                type="critical" if urgent_count > 0 else "info",
                message=f"{len(tickets)} pending fact-check tickets active ({urgent_count} critical SLA breaches pending).",
            )

            return ViewSpec(
                title="Active Rumors & Crisis Queue",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=[
                    HeadingSpec(level=2, text="90-Minute Crisis SLA Incident Queue"),
                    callout,
                    table_spec,
                ],
            )

        if tool_name == "division_rollup":
            divisions_data = data.get("divisions", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            cats = [d.get("division", f"Division {i+1}") for i, d in enumerate(divisions_data)]
            vals = [d.get("composite_index", d.get("district_count", 0.0)) for d in divisions_data]
            tbl_rows = [{"Division": c, "Value": v} for c, v in zip(cats, vals)]
            tbl_spec = DataTableSpec(columns=["Division", "Value"], rows=tbl_rows, caption="Division Breakdown")
            chart_spec = PieChartSpec(
                title="Revenue Division Distribution",
                categories=cats,
                values=vals,
                variant="donut",
                data=[{"name": c, "value": v} for c, v in zip(cats, vals)],
                text_summary=f"Division distribution across {len(cats)} administrative divisions.",
                table_alternative=tbl_spec,
            )
            return ViewSpec(
                title="Division Rollup Overview",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=[
                    HeadingSpec(level=2, text="Administrative Divisions Breakdown"),
                    chart_spec,
                    tbl_spec,
                ],
            )

        if tool_name == "trend":
            trend_points = data.get("points", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            tbl_rows = [{"Date": p.get("date", f"Day {i+1}"), "Score": p.get("score", 0.0)} for i, p in enumerate(trend_points)]
            tbl_spec = DataTableSpec(columns=["Date", "Score"], rows=tbl_rows, caption="Historical Trend")
            chart_spec = LineChartSpec(
                title="Historical Governance Trajectory",
                x_key="day",
                y_key="score",
                data=[{"day": p.get("date", f"Day {i+1}"), "score": p.get("score", 0.0)} for i, p in enumerate(trend_points)],
                text_summary=f"Temporal trend over {len(trend_points)} points.",
                table_alternative=tbl_spec,
            )
            return ViewSpec(
                title="Governance Trajectory Trend",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=[
                    HeadingSpec(level=2, text="Governance Performance Trend"),
                    chart_spec,
                    tbl_spec,
                ],
            )

        if tool_name == "compare_districts":
            districts = data.get("districts", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            chart_data = [{"district": d.get("name_en", d.get("district_code", "")), "score": d.get("composite_index", 0.0)} for d in districts]
            tbl_rows = []
            for d in districts:
                pillars = d.get("pillars", {})
                tbl_rows.append({
                    "District": f"{d.get('name_en', '')} ({d.get('district_code', '')})",
                    "Score": d.get("composite_index", 0.0),
                    "Volume": pillars.get("volume", 0.0),
                    "Sentiment": pillars.get("sentiment", 0.0),
                    "Crisis SLA": pillars.get("crisis_sla", 0.0),
                })
            tbl_spec = DataTableSpec(
                columns=["District", "Score", "Volume", "Sentiment", "Crisis SLA"],
                rows=tbl_rows,
                caption="Multi-District Comparative Index Breakdown",
            )
            chart_spec = BarChartSpec(
                title="Cross-District Governance Index Comparison",
                x_key="district",
                y_key="score",
                data=chart_data,
                text_summary=f"Comparative performance evaluation across {len(districts)} administrative districts.",
                table_alternative=tbl_spec,
            )
            return ViewSpec(
                title="District Comparative Analysis",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=[
                    HeadingSpec(level=2, text="Inter-District Governance Comparison"),
                    chart_spec,
                    tbl_spec,
                ],
            )

        if tool_name == "forecast":
            diff_risk = data.get("diffusion_risk_index", 0.0)
            velocity = data.get("spread_velocity", "MODERATE")
            contagion = data.get("predicted_contagion_districts", [])
            kpis = [
                KpiCardSpec(title="Diffusion Risk Index", value=diff_risk, unit="/1.0", status="critical" if diff_risk >= 0.7 else "neutral"),
                KpiCardSpec(title="Predicted Spread Velocity", value=velocity, status="critical" if velocity == "HIGH" else "neutral"),
            ]
            rows = [{"Contagion District": c, "Risk Horizon": "6-Hour Horizon"} for c in contagion]
            tbl_spec = DataTableSpec(columns=["Contagion District", "Risk Horizon"], rows=rows, caption="Contagion Border Trajectory")
            return ViewSpec(
                title="Predictive AI Rumor Diffusion Forecast",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=[
                    HeadingSpec(level=2, text="Spatio-Temporal Rumor Diffusion Forecast"),
                    CalloutSpec(type="warning", message="Estimated by predictive graph neural diffusion model (heuristic horizon)."),
                    StackSpec(direction="horizontal", children=kpis),
                    tbl_spec,
                ],
            )

        if tool_name == "neighbors":
            nodes = data.get("nodes", []) if isinstance(data, dict) else []
            edges = data.get("edges", []) if isinstance(data, dict) else []
            graph_edges = [{"source": e.get("from", e.get("source", "")), "target": e.get("to", e.get("target", "")), "label": e.get("relation", "BORDERS")} for e in edges]
            edge_rows = [{"Source District": e.get("from", ""), "Adjacent District": e.get("to", ""), "Border Type": e.get("relation", "BORDERS")} for e in edges]
            tbl_spec = DataTableSpec(columns=["Source District", "Adjacent District", "Border Type"], rows=edge_rows, caption="Physical Geographic Border Mesh")
            graph_spec = GraphViewSpec(
                title="District Boundary Contagion Graph",
                nodes=nodes[:100],
                edges=graph_edges[:100],
                text_summary=f"Topology mesh showing {len(nodes)} interconnected boundary nodes and {len(edges)} borders.",
                table_alternative=tbl_spec,
            )
            return ViewSpec(
                title="Geographic Boundary Adjacency Mesh",
                as_of=as_of,
                source_status=status,
                fallback=fallback,
                components=[
                    HeadingSpec(level=2, text="District Border Topology Mesh"),
                    graph_spec,
                    tbl_spec,
                ],
            )

        if tool_name == "dossier_summary":
            d_code = data.get("district_code", "MH-XX")
            score = data.get("composite_index", 0.0)
            kpis = [
                KpiCardSpec(title="Executive Composite Index", value=score, unit="/100", status="positive" if score >= 75 else "neutral"),
            ]
            return ViewSpec(
                title=f"District Executive Dossier: {d_code}",
                as_of=as_of,
                source_status=status,
                district_code=d_code,
                fallback=fallback,
                components=[
                    HeadingSpec(level=2, text=f"District Comprehensive Briefing — {d_code}"),
                    StackSpec(direction="horizontal", children=kpis),
                    TextSpec(content=f"Integrated multi-pillar briefing for district {d_code}."),
                ],
            )

        # Default fallback view for any other tool
        return ViewSpec(
            title=f"Data Summary: {tool_name.replace('_', ' ').title()}",
            as_of=as_of,
            source_status=status,
            fallback=fallback,
            components=[
                HeadingSpec(level=2, text=f"Query Output — {tool_name}"),
                TextSpec(content=f"Report generated as of {as_of} with status '{status}'."),
                DataTableSpec(
                    columns=["Key", "Value"],
                    rows=[{"Key": str(k), "Value": str(v)} for k, v in (data.items() if isinstance(data, dict) else enumerate(data))],
                    caption="Structured Metric Records",
                ),
            ],
        )

    @classmethod
    def build_from_ops(cls, results: List[Any], fallback: bool = False) -> ViewSpec:
        """Compose a unified multi-section ViewSpec from all authorized operation results (§8.1)."""
        from datetime import datetime, timezone

        if not results:
            return cls.build_from_tool_result("league_table", {}, fallback=True)

        all_components: List[AnyComponentSpec] = []
        primary_as_of = datetime.now(timezone.utc).isoformat()
        primary_status = "live"

        for res in results:
            tool = getattr(res, "tool", None) or (res.get("tool") if isinstance(res, dict) else "unknown")
            data = getattr(res, "data", None) or (res.get("data") if isinstance(res, dict) else {})
            if not data:
                continue

            sub_view = cls.build_from_tool_result(tool, data, fallback=fallback)
            primary_as_of = sub_view.as_of
            primary_status = sub_view.source_status
            all_components.extend(sub_view.components)

        if not all_components:
            return cls.build_from_tool_result("league_table", {}, fallback=True)

        return ViewSpec(
            title="Maharashtra Multi-Domain Executive Governance Report",
            as_of=primary_as_of,
            source_status=primary_status,
            fallback=fallback,
            components=all_components,
        )
