"""
Phase 2 Decision Orchestrator (Open-Jev / LLM decision head).
Coordinates multi-agent scheduling, tool selection (search vs scrape vs API),
fallback tiers, and PPO feedback hints according to SAVI Agent Context Spec Section 2.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from savi.config import settings


class OrchestratorDecisionInput(BaseModel):
    user_intent: str
    platforms_requested: List[str] = Field(default_factory=lambda: ["web", "reddit", "twitter", "youtube"])
    mdp_state_summary: Dict[str, Any] = Field(default_factory=dict)
    last_execution_results: Dict[str, Any] = Field(default_factory=dict)
    candidate_urls_from_gemini: List[str] = Field(default_factory=list)
    temporal_window_minutes: float = 15.0
    active_gemini_key_index: int = 0
    notes: Optional[str] = None


class OrchestratorDecisionOutput(BaseModel):
    next_agent: str  # web_search_gemini | web_scrape_firecrawl | reddit | twitter | youtube | none
    action: str      # search | scrape | api | backoff | rotate_key | rotate_proxy | switch_parser
    target: str      # query string, URL, subreddit, video_id, or status URL
    parser_mode: str # api | firecrawl | headless | apify
    priority: int = 1
    parallel_agents: List[str] = Field(default_factory=list)
    macro_cascade_hint: bool = False
    ppo_action_hint: Optional[str] = None  # INCREASE_DELAY | SWITCH_PARSER | SOFT_BACKOFF | ROTATE_KEY | null
    fallback_tier: int = 1
    reasoning: str


class DecisionOrchestrator:
    """
    Open-Jev Decision Engine:
    Evaluates current state, rate limit triggers, candidate URLs, and platform needs
    to issue the optimal operational decision for the quad-agent mesh.
    """
    def __init__(self):
        self.model_id = "ZefanCai/Open-Jev-2B"

    def plan_next_step(self, plan_input: OrchestratorDecisionInput) -> OrchestratorDecisionOutput:
        """
        Determines the next agent, execution tier, and PPO action hint
        based on the decision rubric in §2.4 & §0.1.3 of context.md.
        """
        last_results = plan_input.last_execution_results
        web_res = last_results.get("web", {})
        key_idx = plan_input.active_gemini_key_index

        # Check for 429 rate limits or quota exhaustion
        hit_429 = any(res.get("hit_429_rate_limit", False) for res in last_results.values())
        hit_captcha = any(res.get("hit_captcha_challenge", False) for res in last_results.values())

        # Rule 1: Handle rate limits with PPO Key Rotation or Soft Backoff
        if hit_429:
            if key_idx == 0:
                return OrchestratorDecisionOutput(
                    next_agent="web_search_gemini",
                    action="rotate_key",
                    target=plan_input.user_intent,
                    parser_mode="api",
                    priority=1,
                    ppo_action_hint="ROTATE_KEY",
                    fallback_tier=2,
                    reasoning="HTTP 429 / quota detected on primary Gemini key. Rotating to secondary GEMINI_API_KEY_2 (Tier 2).",
                )
            else:
                return OrchestratorDecisionOutput(
                    next_agent="web_scrape_firecrawl",
                    action="backoff",
                    target=plan_input.user_intent,
                    parser_mode="firecrawl",
                    priority=1,
                    ppo_action_hint="SOFT_BACKOFF",
                    fallback_tier=3,
                    reasoning="Multiple rate limits encountered across primary and secondary keys. Triggering soft backoff.",
                )

        # Rule 2: Handle Captchas by switching parser strategy
        if hit_captcha:
            return OrchestratorDecisionOutput(
                next_agent="web_scrape_firecrawl",
                action="switch_parser",
                target=plan_input.candidate_urls_from_gemini[0] if plan_input.candidate_urls_from_gemini else plan_input.user_intent,
                parser_mode="firecrawl",
                priority=1,
                ppo_action_hint="SWITCH_PARSER",
                fallback_tier=2,
                reasoning="Captcha / bot wall encountered on native DOM parser. Switching parser mode to Firecrawl.",
            )

        # Rule 3: Web Discovery -> Scrape Handover
        if plan_input.candidate_urls_from_gemini:
            # URLs discovered, ready for Firecrawl extraction
            target_url = plan_input.candidate_urls_from_gemini[0]
            parallel = [p for p in plan_input.platforms_requested if p in ["reddit", "twitter", "youtube"]]
            return OrchestratorDecisionOutput(
                next_agent="web_scrape_firecrawl",
                action="scrape",
                target=target_url,
                parser_mode="firecrawl",
                priority=1,
                parallel_agents=parallel,
                macro_cascade_hint=len(parallel) > 1,
                ppo_action_hint=None,
                fallback_tier=1,
                reasoning=f"Discovered candidate URLs from Gemini. Dispatching Firecrawl to extract sanitized article from {target_url}.",
            )

        # Rule 4: Initial Step -> Initiate Gemini Search Discovery
        if "web" in plan_input.platforms_requested:
            parallel = [p for p in plan_input.platforms_requested if p != "web"]
            return OrchestratorDecisionOutput(
                next_agent="web_search_gemini",
                action="search",
                target=plan_input.user_intent,
                parser_mode="api",
                priority=1,
                parallel_agents=parallel,
                macro_cascade_hint=True,
                ppo_action_hint=None,
                fallback_tier=1,
                reasoning="Initial query step: executing Gemini discovery with Google Search grounding to identify authoritative URLs.",
            )

        # Default fallback
        first_plat = plan_input.platforms_requested[0] if plan_input.platforms_requested else "none"
        return OrchestratorDecisionOutput(
            next_agent=first_plat,
            action="api",
            target=plan_input.user_intent,
            parser_mode="api",
            priority=1,
            parallel_agents=[],
            macro_cascade_hint=False,
            ppo_action_hint=None,
            fallback_tier=1,
            reasoning=f"Routing directly to primary platform {first_plat}.",
        )
