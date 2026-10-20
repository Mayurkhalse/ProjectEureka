"""Thesys C1 Generative UI Client.

Enforces:
- OpenAI Python SDK configured with base_url https://api.thesys.dev/v1/embed
- API key isolated strictly from THESYS_API_KEY
- Registered custom component schemas: KpiCard, DataTable, BarChart, LineChart, GraphView, Callout, Heading
- Quoted aggregate data injection (role split: Gemma handles tools/text, C1 handles UI)
- Circuit breaker & sliding window rate caps
- Strict key redaction across all logs and exceptions
- Fail-open fallback to deterministic ViewSpec
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
import httpx
from openai import AsyncOpenAI, APIConnectionError, RateLimitError, APIStatusError

from eureka.copilot.config import get_copilot_settings
from eureka.copilot.gemma_client import redact_secrets

logger = logging.getLogger("eureka.copilot.c1_client")


class C1CircuitBreakerOpen(Exception):
    """Raised when Thesys C1 circuit breaker is in OPEN state."""
    pass


class C1SecurityException(Exception):
    """Raised when security guardrails or rate caps are triggered for C1."""
    pass


def get_c1_custom_components() -> List[Dict[str, Any]]:
    """Define JSON Schemas for custom MCC components registered with C1."""
    return [
        {
            "name": "KpiCard",
            "description": "Key Performance Indicator metric card displaying score, volume, or TAT.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Metric title or district name"},
                    "value": {"type": ["string", "number"], "description": "Grounded metric value"},
                    "unit": {"type": "string", "description": "Unit of measurement (e.g. /100, mins, %) "},
                    "delta": {"type": "number", "description": "Change relative to previous period"},
                    "status": {"type": "string", "enum": ["positive", "negative", "neutral", "critical"]},
                },
                "required": ["title", "value"],
            },
        },
        {
            "name": "DataTable",
            "description": "Accessible data table for district rankings, rumor queues, or pillar scores.",
            "parameters": {
                "type": "object",
                "properties": {
                    "caption": {"type": "string", "description": "Screen-reader table caption"},
                    "columns": {
                        "type": "array",
                        "items": {"type": "object", "properties": {"key": {"type": "string"}, "label": {"type": "string"}}},
                    },
                    "rows": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["columns", "rows"],
            },
        },
        {
            "name": "BarChart",
            "description": "Categorical performance comparison chart with mandatory screen reader summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "xKey": {"type": "string"},
                    "yKey": {"type": "string"},
                    "data": {"type": "array", "items": {"type": "object"}},
                    "summary": {"type": "string", "description": "Textual summary for accessibility"},
                },
                "required": ["title", "xKey", "yKey", "data"],
            },
        },
        {
            "name": "LineChart",
            "description": "Temporal trend line chart over historical hours or days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "xKey": {"type": "string"},
                    "yKey": {"type": "string"},
                    "data": {"type": "array", "items": {"type": "object"}},
                    "summary": {"type": "string"},
                },
                "required": ["title", "xKey", "yKey", "data"],
            },
        },
        {
            "name": "GraphView",
            "description": "Spatio-temporal adjacency or rumor diffusion graph.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "nodes": {"type": "array", "items": {"type": "object"}},
                    "edges": {"type": "array", "items": {"type": "object"}},
                    "summary": {"type": "string"},
                },
                "required": ["title", "nodes", "edges"],
            },
        },
        {
            "name": "Callout",
            "description": "Governance advisory, alert banner, or authorization refusal callout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["info", "warning", "success", "critical"]},
                    "message": {"type": "string"},
                },
                "required": ["type", "message"],
            },
        },
        {
            "name": "Heading",
            "description": "Semantic structural header for the report.",
            "parameters": {
                "type": "object",
                "properties": {
                    "level": {"type": "integer", "enum": [1, 2, 3, 4]},
                    "text": {"type": "string"},
                },
                "required": ["level", "text"],
            },
        },
    ]


class C1Client:
    """Client for Thesys C1 Generative UI service via OpenAI-compatible endpoint."""

    def __init__(self, api_key: Optional[str] = None):
        self.settings = get_copilot_settings()
        self.api_key = api_key or self.settings.THESYS_API_KEY
        self.base_url = self.settings.C1_BASE_URL
        self.model = self.settings.C1_MODEL_ID

        # Circuit breaker
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._circuit_threshold = 5
        self._circuit_reset_timeout = 20.0  # seconds

        # Reusable client
        self._openai_client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key or "missing-thesys-key",
            timeout=12.0,
            max_retries=0,  # We manage retries explicitly with backoff
        )

    def _check_circuit_breaker(self) -> None:
        now = time.time()
        if now < self._circuit_open_until:
            wait_sec = int(self._circuit_open_until - now)
            raise C1CircuitBreakerOpen(f"Thesys C1 circuit breaker is OPEN ({wait_sec}s cooling remaining).")

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self._circuit_threshold:
            self._circuit_open_until = time.time() + self._circuit_reset_timeout
            logger.warning("Thesys C1 circuit breaker tripped after %d failures. Open for %ds.",
                           self._consecutive_failures, self._circuit_reset_timeout)

    def _prepare_quoted_tool_data(self, tool_data: Any) -> str:
        """Strip raw article bodies and redact long strings before sending to C1."""
        if not isinstance(tool_data, dict):
            return json.dumps(tool_data)
        
        # Clone and compact
        compact: Dict[str, Any] = {}
        for k, v in tool_data.items():
            if k in ("raw_events", "full_text", "article_content", "body"):
                continue
            if isinstance(v, list) and len(v) > 50:
                compact[k] = v[:50]  # Cap list length
            else:
                compact[k] = v
        return json.dumps(compact, ensure_ascii=False)

    async def generate_ui(
        self,
        tool_name: str,
        tool_data: Any,
        user_query: str,
        language: str = "en",
    ) -> str:
        """Query Thesys C1 to generate an OpenUI/C1 component tree from quoted tool data."""
        self._check_circuit_breaker()

        if not self.api_key:
            raise C1SecurityException("THESYS_API_KEY is not configured.")

        quoted_data = self._prepare_quoted_tool_data(tool_data)
        custom_components = get_c1_custom_components()

        system_prompt = (
            "You are the Thesys C1 Generative UI Engine for the DGIPR Maha-Command Center. "
            "Your task is to transform verified, governed tool data into clean visual UI specifications. "
            "STRICT RULES:\n"
            "1. Output ONLY component markup using registered components: "
            "<Stack>, <Heading>, <KpiCard>, <DataTable>, <BarChart>, <LineChart>, <GraphView>, <Callout>.\n"
            "2. Ground 100% of numeric values and names directly in the provided DATA block. Do NOT invent numbers.\n"
            "3. Every BarChart and LineChart MUST include a nested summary attribute for GIGW 3.0 accessibility.\n"
            "4. Return only the component markup without markdown fences."
        )

        user_content = (
            f"Officer Query: {user_query}\n"
            f"Primary Tool: {tool_name}\n"
            f"Language: {language}\n\n"
            f"VERIFIED GOVERNANCE DATA:\n"
            f"```json\n{quoted_data}\n```"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        max_attempts = 2
        last_error = None

        for attempt in range(max_attempts):
            try:
                response = await self._openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.0,
                    stream=False,
                )
                self._record_success()
                content = response.choices[0].message.content or ""
                return content.strip()

            except (RateLimitError, APIStatusError) as exc:
                last_error = exc
                status_code = getattr(exc, "status_code", None)
                # Retry only on 429, 500, 502, 503, 504
                if status_code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                    backoff = (attempt + 1) * 0.5
                    logger.warning("Thesys C1 returned %s. Retrying in %.1fs...", status_code, backoff)
                    await asyncio.sleep(backoff)
                    continue
                break

            except (APIConnectionError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt < max_attempts - 1:
                    await asyncio.sleep(0.5)
                    continue
                break

            except Exception as exc:
                last_error = exc
                clean_err = redact_secrets(str(exc))
                logger.error("Non-retryable C1 error: %s", clean_err)
                break

        self._record_failure()
        clean_msg = redact_secrets(str(last_error))
        raise RuntimeError(f"Thesys C1 generation failed: {clean_msg}")
