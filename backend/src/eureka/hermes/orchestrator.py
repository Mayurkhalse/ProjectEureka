"""Hermes Orchestrator for Project EUREKA.

Provides programmatic dispatch to the NousResearch Hermes Agent with:
1. Documented Hermes API Server interface (HTTP + SSE on port 8642).
2. Fallback to official one-shot CLI (`hermes -z <prompt>`).
3. Strict enforcement of the Agent Autonomy Boundary:
   - Allowlisted agent tools: drafting (`tool_stage_dm_rebuttal`), translation (`tool_translate_and_normalize`), graph sync (`tool_sync_neo4j_nodes`).
   - Human approval required: consequential signoffs (`tool_execute_dm_signoff`) cannot be autonomously invoked by the agent.
4. Truthful availability reporting: never masks Hermes offline status or falsely claims Hermes ran when a fallback is used.
"""

import json
import logging
import os
from typing import Any, Callable, Dict, List, Optional
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

logger = logging.getLogger("eureka.hermes.orchestrator")

from eureka.hermes.agent_tools import (
    AGENT_ALLOWLISTED_TOOLS,
    AGENT_TOOL_DEFINITIONS,
    AGENT_TOOL_MAP,
    tool_stage_dm_rebuttal,
    tool_sync_neo4j_nodes,
    tool_translate_and_normalize,
)
from eureka.hermes.hermes_client import (
    HermesAPIError,
    HermesClient,
    HermesError,
    HermesTimeoutError,
    HermesUnavailableError,
    get_hermes_client,
)

SYSTEM_PROMPT = """You are Hermes, the AI governance assistant for Project EUREKA (DGIPR Maha-Command Center, Mantralaya).
Your scope is strictly limited to fact analysis, regional Indic translation, and drafting factual rebuttals for 36 Maharashtra districts.
GUARDRAILS:
1. You may draft and stage rebuttal notes in 'pending_review' status.
2. You CANNOT authorize, approve, or sign off on crisis tickets autonomously. Consequential sign-off is reserved strictly for authenticated human District Magistrates/Collectors.
3. Keep all outputs audit-grade and zero-slop."""


class HermesOrchestrator:
    """Orchestrates Project EUREKA governance workflows using the real Hermes Agent."""

    def __init__(self, client: Optional[HermesClient] = None):
        self.client = client or get_hermes_client()

    def check_health(self) -> Dict[str, Any]:
        """Checks connectivity to the Hermes API Server and local CLI binary."""
        api_health = self.client.check_health()
        cli_available = bool(self.client.cli_bin)
        is_online = api_health.get("status") == "online"

        return {
            "status": "online" if is_online else ("cli_only" if cli_available else "offline"),
            "hermes_available": is_online or cli_available,
            "api_server": api_health,
            "cli_bin": self.client.cli_bin,
            "cli_available": cli_available,
        }

    def run_agent_turn(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        session_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sends a governance task prompt to the Hermes Agent API server or CLI.

        Returns:
            Dict containing the real response and engine status.
        Raises:
            HermesUnavailableError: When neither API server nor CLI can complete the turn.
        """
        ctx = context or {}
        user_content = prompt
        if ctx:
            user_content = f"{prompt}\n\nTask Context: {json.dumps(ctx, ensure_ascii=False)}"

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        # 1. Try documented Hermes API Server
        try:
            resp = self.client.chat_completions(
                messages=messages,
                session_id=session_id,
                session_key=session_key,
            )
            choices = resp.get("choices", [])
            content = choices[0]["message"]["content"] if choices else ""
            return {
                "hermes_available": True,
                "engine": "hermes_api_server",
                "model": resp.get("model", "hermes-agent"),
                "output": content,
                "raw_response": resp,
            }
        except (HermesUnavailableError, HermesTimeoutError) as exc:
            logger.info("Hermes API server not accessible (%s). Attempting CLI one-shot...", exc)

        # 2. Try official Hermes one-shot CLI mode (-z)
        if self.client.cli_bin:
            try:
                cli_output = self.client.execute_cli_oneshot(prompt, timeout_sec=15.0)
                return {
                    "hermes_available": True,
                    "engine": "hermes_cli_oneshot",
                    "output": cli_output,
                }
            except Exception as cli_exc:
                logger.info("Hermes CLI one-shot invocation unavailable: %s", cli_exc)

        # 3. Hermes is unavailable
        raise HermesUnavailableError(
            f"Hermes Agent is unavailable: API server unreachable at {self.client.base_url} "
            f"and local CLI execution failed."
        )

    def run_task(
        self,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        allow_fallback: bool = True,
    ) -> Dict[str, Any]:
        """Main orchestrator entrypoint.

        Enforces:
        - Strict prohibition on autonomous consequential sign-off.
        - Dispatch to real Hermes agent when online.
        - Truthful reporting of availability without faking.
        - Staging of allowlisted domain tools (draft rebuttal, translation, neo4j sync).
        """
        ctx = context or {}
        p_lower = prompt.lower()

        # Step 1: Guardrail: Prevent Autonomous Signoff
        # Consequential human actions must not be bypassed by the agent
        if any(term in p_lower for term in ["signoff", "sign-off", "authorize", "approve"]):
            # Check if this is an attempt to autonomously sign off a ticket
            if "stage" not in p_lower and "draft" not in p_lower:
                err_msg = (
                    "Agent Autonomy Violation: Autonomous sign-off is strictly prohibited. "
                    "Consequential approvals must be authorized by an authenticated District Collector "
                    "or DG Admin via the /api/v1/hermes/dm-pipelines/{ticket_id}/action desk."
                )
                logger.warning(err_msg)
                raise PermissionError(err_msg)

        # Step 2: Attempt Real Hermes Agent Execution
        hermes_result: Optional[Dict[str, Any]] = None
        hermes_error: Optional[str] = None

        try:
            hermes_result = self.run_agent_turn(prompt=prompt, context=ctx)
        except HermesUnavailableError as exc:
            hermes_error = str(exc)
            if not allow_fallback:
                raise

        # Step 3: Execute Narrowly Allowlisted Staging Tools
        tool_result: Optional[Dict[str, Any]] = None
        tool_called: Optional[str] = None

        # 3a. Translate & Normalize
        if "translate" in p_lower or "normalize" in p_lower:
            text = ctx.get("raw_text") or ctx.get("text") or prompt
            tool_called = "tool_translate_and_normalize"
            tool_result = tool_translate_and_normalize(text)

        # 3b. Stage DM Rebuttal (Drafting only, status=pending_review)
        elif "stage" in p_lower or "rebuttal" in p_lower or "draft" in p_lower:
            ticket_id = ctx.get("ticket_id") or "TKT-GEN-001"
            district_code = ctx.get("district_code") or "MH-04"
            # Use Hermes-generated draft if available, else context draft or placeholder
            draft_text = (
                (hermes_result.get("output") if hermes_result else None)
                or ctx.get("draft_text")
                or f"Official factual clarification for {district_code} regarding verified facts."
            )
            tool_called = "tool_stage_dm_rebuttal"
            tool_result = tool_stage_dm_rebuttal(
                ticket_id=ticket_id,
                district_code=district_code,
                draft_text=draft_text,
            )

        # 3c. Neo4j Node Sync (Idempotent merge)
        elif "neo4j" in p_lower or "graph" in p_lower or "sync" in p_lower:
            district_code = ctx.get("district_code") or "MH-12"
            event_id = ctx.get("event_id") or "EVT-TEST-001"
            claim_text = ctx.get("claim_text") or "Verified administrative announcement."
            tool_called = "tool_sync_neo4j_nodes"
            tool_result = tool_sync_neo4j_nodes(
                district_code=district_code,
                event_id=event_id,
                claim_text=claim_text,
            )

        # Step 4: Assemble Response with Truth in Execution
        if hermes_result:
            return {
                "status": "success",
                "hermes_available": True,
                "engine": hermes_result.get("engine", "hermes_api_server"),
                "agent_response": hermes_result.get("output"),
                "tool_called": tool_called,
                "tool_result": tool_result,
                "context": ctx,
            }

        # Fallback executed: Truthful reporting
        return {
            "status": "success",
            "hermes_available": False,
            "engine": "deterministic_staging_fallback",
            "warning": (
                "Hermes Agent was offline or unreachable. "
                "Executed deterministic staging fallback under allowlisted guardrails."
            ),
            "hermes_error": hermes_error,
            "tool_called": tool_called,
            "tool_result": tool_result,
            "context": ctx,
        }


_orchestrator = HermesOrchestrator()


def get_hermes_orchestrator() -> HermesOrchestrator:
    return _orchestrator
