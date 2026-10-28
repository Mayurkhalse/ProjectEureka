"""Structured Operation and Plan Models for Query Decomposition.

Strict Pydantic models for individual operations (Op), full plans (Plan),
and parsed queries (ParsedQuery).
"""

from typing import Any, Dict, Literal, Tuple
from pydantic import BaseModel, ConfigDict

from eureka.copilot.policy.matrix import Intent

ToolName = Literal[
    "league_table",
    "district_profile",
    "pillar_breakdown",
    "trend",
    "compare_districts",
    "active_rumors",
    "forecast",
    "neighbors",
    "division_rollup",
    "dossier_summary",
]


class Op(BaseModel):
    """An individual typed, candidate operation resulting from query decomposition."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    op_id: str                                  # "o1", "o2", etc.
    intent: Intent
    tool: ToolName
    args: Dict[str, Any]
    districts: Tuple[str, ...]                  # Normalized MH-XX district codes
    group: str                                  # Composition group identifier (e.g. "MH-23:crisis")
    label: str                                  # UI plan chip label (e.g. "Dhule · Crisis")
    depends_on: Tuple[str, ...] = ()
    defaulted_scope: bool = False               # True if district was inferred from principal context
    source: Literal["parser", "llm"] = "parser"


class Plan(BaseModel):
    """An ordered set of candidate operations."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    ops: Tuple[Op, ...]


class ParsedQuery(BaseModel):
    """Output of deterministic query parsing with confidence and residual terms."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    ops: Tuple[Op, ...]
    confidence: float                           # 0.0 to 1.0
    residual_tokens: Tuple[str, ...]            # Words not accounted for by any rule
    clarifications: Tuple[str, ...] = ()        # E.g. ("compare_needs_two_districts",)
