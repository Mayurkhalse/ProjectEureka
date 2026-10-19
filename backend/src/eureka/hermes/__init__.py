"""Hermes: District Magistrate (DM) Pipeline Manager & Crisis SLA Dispatcher for Project EUREKA."""

from eureka.hermes.dm_pipeline_manager import HermesDMPipelineManager
from eureka.hermes.orchestrator import HermesOrchestrator, get_hermes_orchestrator
from eureka.hermes.hermes_client import (
    HermesClient,
    get_hermes_client,
    HermesError,
    HermesUnavailableError,
    HermesTimeoutError,
    HermesAPIError,
)
from eureka.hermes.agent_tools import (
    AGENT_ALLOWLISTED_TOOLS,
    AGENT_TOOL_DEFINITIONS,
    AGENT_TOOL_MAP,
    tool_translate_and_normalize,
    tool_stage_dm_rebuttal,
    tool_execute_dm_signoff,
    tool_sync_neo4j_nodes,
)

__all__ = [
    "HermesDMPipelineManager",
    "HermesOrchestrator",
    "get_hermes_orchestrator",
    "HermesClient",
    "get_hermes_client",
    "HermesError",
    "HermesUnavailableError",
    "HermesTimeoutError",
    "HermesAPIError",
    "AGENT_ALLOWLISTED_TOOLS",
    "AGENT_TOOL_DEFINITIONS",
    "AGENT_TOOL_MAP",
    "tool_translate_and_normalize",
    "tool_stage_dm_rebuttal",
    "tool_execute_dm_signoff",
    "tool_sync_neo4j_nodes",
]
