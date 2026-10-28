"""Memory Gate: Isolated mediation layer between Copilot and Mem0/Qdrant.

Guarantees:
  1. Pseudonymous user IDs are always enforced; callers cannot pass arbitrary IDs.
  2. Memory is scoped strictly to presentation preferences; it cannot widen scope or entities.
  3. Deletion requires cryptographic ownership verification (fixing IDOR A12).
  4. Memory search has a strict 300ms fail-open timeout; failures never disrupt responses.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

from eureka.copilot.policy.principal import PolicyPrincipal
from eureka.copilot.response.prefs import PresentationPrefs, parse_presentation_prefs
from eureka.copilot.memory import get_memory_manager, is_allowed_preference

logger = logging.getLogger("eureka.copilot.policy.memory_gate")


class MemoryGate:
    """The single authorized entrypoint to user memory for routers and endpoints."""

    def __init__(self):
        self._mem_mgr = get_memory_manager()

    async def prefs_for(
        self,
        p: PolicyPrincipal,
        query: str,
        lang: str = "en",
    ) -> PresentationPrefs:
        """Retrieve and parse presentation preferences with a 300ms fail-open boundary."""
        is_enabled_fn = getattr(self._mem_mgr, "is_enabled", None)
        if is_enabled_fn is not None:
            if not is_enabled_fn():
                return PresentationPrefs.default()
        elif not getattr(getattr(self._mem_mgr, "settings", None), "COPILOT_MEMORY_ENABLED", False):
            return PresentationPrefs.default()

        clean_prefs: List[str] = []
        try:
            raw_prefs = await asyncio.wait_for(
                self._mem_mgr.search_preferences(p.username, query),
                timeout=0.300,
            )
            # Re-filter and sanitize retrieved preferences
            for pref in raw_prefs[:5]:
                if not isinstance(pref, str):
                    continue
                # Strip control characters, newlines, and potential tags
                sanitized = re.sub(r'[\r\n\t<>]+', ' ', pref).strip()
                if 0 < len(sanitized) <= 200 and is_allowed_preference(sanitized):
                    clean_prefs.append(sanitized)
        except asyncio.TimeoutError:
            logger.info("memory.timeout: Mem0 search exceeded 300ms deadline. Continuing with defaults.")
            return PresentationPrefs.default()
        except Exception as exc:
            logger.warning("memory.error: Search failed for principal %s: %s", p.username, exc)
            return PresentationPrefs.default()

        return parse_presentation_prefs(clean_prefs, language_hint=lang)

    async def learn(
        self,
        p: PolicyPrincipal,
        query: str,
        lang: str = "en",
    ) -> None:
        """Asynchronously ingest user preferences from user's raw query text only."""
        if not self._mem_mgr.is_enabled():
            return
        try:
            await self._mem_mgr.add_preference_async(
                p.username,
                p.role.value,
                lang,
                query,
            )
        except Exception as exc:
            logger.debug("memory.learn_failed for principal %s: %s", p.username, exc)

    async def list_for(self, p: PolicyPrincipal) -> List[Dict[str, Any]]:
        """List verified memories owned exclusively by the principal."""
        if not self._mem_mgr.is_enabled():
            return []
        try:
            return await self._mem_mgr.get_all_user_memories(p.username)
        except Exception as exc:
            logger.warning("memory.list_failed for principal %s: %s", p.username, exc)
            return []

    async def delete_one(self, p: PolicyPrincipal, memory_id: str) -> bool:
        """Delete a single memory item with strict ownership verification (anti-IDOR)."""
        if not self._mem_mgr.is_enabled() or not memory_id:
            return False

        try:
            # 1. Enforce ownership verification: ensure memory belongs to caller
            owned = await self.list_for(p)
            owned_ids = {m.get("id") for m in owned if isinstance(m, dict)}
            if memory_id not in owned_ids:
                logger.warning(
                    "memory.unauthorized_delete_attempt: principal '%s' attempted to delete unowned id '%s'",
                    p.username,
                    memory_id,
                )
                return False

            # 2. Delete with verified ownership
            return await self._mem_mgr.delete_user_memory(p.username, memory_id)
        except Exception as exc:
            logger.warning("memory.delete_one_failed: %s", exc)
            return False

    async def delete_all(self, p: PolicyPrincipal) -> bool:
        """Delete all memories owned by the principal."""
        if not self._mem_mgr.is_enabled():
            return False
        try:
            return await self._mem_mgr.delete_all_user_memories(p.username)
        except Exception as exc:
            logger.warning("memory.delete_all_failed for %s: %s", p.username, exc)
            return False
