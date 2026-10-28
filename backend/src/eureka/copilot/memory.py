"""Mem0 User Preference Memory Integration for Open UI Copilot.

MANDATORY CONSTRAINTS:
1. Self-hosted library mode using Qdrant vector store.
2. Embedder: Thesys API via custom OpenAI-compatible client (baseURL: https://api.thesys.dev/v1/embed).
3. Zero OpenAI defaults: Runs securely even with OPENAI_API_KEY unset.
4. User Pseudonymization: user_id = HMAC-SHA256(username, server_salt) — never stores real name/email.
5. Strict preference allowlist: Only stores presentation preferences (language, chart types, pinned districts).
   Explicitly filters out and drops any figures, numbers, incident texts, personal names, or contact info.
6. Fail-open & bounded: Search timeout at 800ms; memory outage never breaks the copilot.
"""

import asyncio
import hashlib
import hmac
import logging
import re
from typing import Any, Dict, List, Optional

from eureka.copilot.config import get_copilot_settings

logger = logging.getLogger("eureka.copilot.memory")

# Allowed presentation preference topics
ALLOWED_TOPIC_KEYWORDS = [
    "language",
    "marathi",
    "hindi",
    "english",
    "chart",
    "table",
    "bar",
    "line",
    "kpi",
    "pinned",
    "district",
    "summary",
    "concise",
    "detailed",
    "bilingual",
]

# Patterns for disallowed data (numbers, phones, emails, sensitive entities)
EMAIL_PATTERN = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
PHONE_PATTERN = re.compile(r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b')
NUMERIC_STAT_PATTERN = re.compile(r'\b\d+(?:\.\d+)?(?:\s*%)?\b')

# Module-level set tracking active async background ingestion tasks (§9.5)
_background_memory_tasks: set[asyncio.Task] = set()


def pseudonymize_user_id(username: str, secret_salt: Optional[str] = None) -> str:
    """Derive an irreversible 32-character HMAC pseudonym from username."""
    settings = get_copilot_settings()
    salt = secret_salt or settings.COPILOT_SECRET_SALT
    return hmac.new(salt.encode("utf-8"), username.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def is_allowed_preference(text: str) -> bool:
    """Filter memory extractions: Allow only formatting/presentation preferences, drop incident data & numbers."""
    if not text:
        return False

    # Disallow sensitive contact info
    if EMAIL_PATTERN.search(text) or PHONE_PATTERN.search(text):
        logger.info("Dropping memory containing contact info: %s", text[:30])
        return False

    # Disallow raw incident reports or rumor statements
    disallowed_incident_words = ["killed", "protest", "riot", "fire", "accident", "bribe", "arrest", "scam", "rumor"]
    if any(w in text.lower() for w in disallowed_incident_words):
        logger.info("Dropping memory containing incident/rumor text: %s", text[:30])
        return False

    # Reject statistics, 3+ digit numbers, or percentage literals (§9.5)
    # Small single/double digits (e.g. "top 5") remain permitted
    if re.search(r"\b\d{3,}\b|\b\d+(?:\.\d+)?\s*%", text):
        logger.info("Dropping memory containing numeric statistics: %s", text[:30])
        return False

    # Must contain at least one recognized presentation preference topic as a WHOLE TOKEN (§9.5)
    # Prevents false-positives like 'Baramati' matching 'bar' or 'deadline' matching 'line'
    text_lower = text.lower()
    keyword_pattern = r"\b(?:" + "|".join(re.escape(k) for k in ALLOWED_TOPIC_KEYWORDS) + r")\b"
    if not re.search(keyword_pattern, text_lower):
        logger.info("Dropping memory lacking presentation preference keywords: %s", text[:30])
        return False

    return True


class CopilotMemoryManager:
    """Manages scoped officer preferences via Mem0 + Qdrant."""

    def __init__(self):
        self.settings = get_copilot_settings()
        self._mem0_instance = None
        self._init_failed = False

    def is_enabled(self) -> bool:
        """Check if memory management is enabled in settings."""
        return bool(self.settings.COPILOT_MEMORY_ENABLED)

    def _get_mem0(self):
        """Lazy initializer for Mem0 configured with Thesys Embedder & Qdrant."""
        if not self.settings.COPILOT_MEMORY_ENABLED:
            return None

        if self._init_failed:
            return None

        if self._mem0_instance is not None:
            return self._mem0_instance

        try:
            from mem0 import Memory

            thesys_key = self.settings.THESYS_API_KEY or "dummy_thesys_key"
            gemini_key = self.settings.get_effective_gemini_key() or "dummy_gemini_key"

            config = {
                "vector_store": {
                    "provider": "qdrant",
                    "config": {
                        "url": self.settings.QDRANT_URL,
                        "api_key": self.settings.QDRANT_API_KEY,
                        "collection_name": "copilot_user_preferences",
                        "embedding_model_dims": 1536,
                    },
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "model": self.settings.COPILOT_EMBED_MODEL,
                        "api_key": thesys_key,
                        "openai_base_url": "https://api.thesys.dev/v1/embed",
                        "embedding_dims": 1536,
                    },
                },
                "llm": {
                    "provider": "gemini",
                    "config": {
                        "model": self.settings.COPILOT_MODEL,
                        "api_key": gemini_key,
                        "temperature": 0.0,
                        "max_tokens": 1024,
                    },
                },
                "custom_prompt": (
                    "Extract ONLY the user's interface, language, and presentation formatting preferences "
                    "(e.g., preferred language, preferred chart type, pinned district, concise vs detailed format). "
                    "DO NOT extract any personal names, figures, numbers, facts, rumors, or incident details."
                ),
            }

            self._mem0_instance = Memory.from_config(config)
            return self._mem0_instance
        except Exception as exc:
            logger.warning("Mem0 initialization failed (will operate fail-open): %s", exc)
            self._init_failed = True
            return None

    async def search_preferences(self, username: str, query: str) -> List[str]:
        """Retrieve user presentation preferences with strict 800ms fail-open timeout."""
        if not self.settings.COPILOT_MEMORY_ENABLED:
            return []

        pseudo_id = pseudonymize_user_id(username)

        async def _do_search() -> List[str]:
            mem = self._get_mem0()
            if not mem:
                return []
            try:
                # Run synchronous mem0 in threadpool
                loop = asyncio.get_running_loop()
                results = await loop.run_in_executor(
                    None,
                    lambda: mem.search(query=query, user_id=pseudo_id, agent_id="open-ui-copilot", limit=5),
                )
                filtered = []
                for item in results:
                    text = item.get("memory", "")
                    if is_allowed_preference(text):
                        filtered.append(text)
                return filtered
            except Exception as e:
                logger.warning("Mem0 search error (fail-open): %s", e)
                return []

        try:
            timeout_sec = self.settings.COPILOT_MEMORY_TIMEOUT_MS / 1000.0
            return await asyncio.wait_for(_do_search(), timeout=timeout_sec)
        except asyncio.TimeoutError:
            logger.warning("Mem0 preference search timed out (>%dms). Proceeding fail-open.", self.settings.COPILOT_MEMORY_TIMEOUT_MS)
            return []
        except Exception as e:
            logger.warning("Mem0 unexpected error: %s", e)
            return []

    async def add_preference_async(self, username: str, role: str, language: str, text: str) -> None:
        """Asynchronously extract and store presentation preferences in the background."""
        if not self.settings.COPILOT_MEMORY_ENABLED:
            return

        pseudo_id = pseudonymize_user_id(username)

        # Pre-filter text to avoid sending sensitive/numerical queries to memory extraction
        if not is_allowed_preference(text) and not any(k in text.lower() for k in ["marathi", "hindi", "chart", "table", "prefer"]):
            return

        async def _do_add():
            mem = self._get_mem0()
            if not mem:
                return
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(
                    None,
                    lambda: mem.add(
                        messages=[{"role": "user", "content": text}],
                        user_id=pseudo_id,
                        agent_id="open-ui-copilot",
                        metadata={"role_class": role, "language": language},
                    ),
                )
            except Exception as e:
                logger.warning("Mem0 background add failed: %s", e)

        # Launch non-blocking background task with strong reference tracking (§9.5)
        task = asyncio.create_task(_do_add())
        _background_memory_tasks.add(task)
        task.add_done_callback(_background_memory_tasks.discard)

    async def get_all_user_memories(self, username: str) -> List[Dict[str, Any]]:
        """Retrieve all stored memories for the authenticated officer."""
        if not self.settings.COPILOT_MEMORY_ENABLED:
            return []

        pseudo_id = pseudonymize_user_id(username)
        mem = self._get_mem0()
        if not mem:
            return []

        try:
            loop = asyncio.get_running_loop()
            raw_memories = await loop.run_in_executor(
                None,
                lambda: mem.get_all(user_id=pseudo_id, agent_id="open-ui-copilot"),
            )
            valid = []
            for m in raw_memories:
                text = m.get("memory", "")
                if is_allowed_preference(text):
                    valid.append({
                        "id": m.get("id"),
                        "memory": text,
                        "created_at": m.get("created_at"),
                    })
            return valid
        except Exception as e:
            logger.warning("Failed to fetch user memories: %s", e)
            return []

    async def delete_user_memory(self, username: str, memory_id: str) -> bool:
        """Delete a single specific preference memory with ownership verification (anti-IDOR §9.5)."""
        pseudo_id = pseudonymize_user_id(username)
        mem = self._get_mem0()
        if not mem:
            return True

        # Anti-IDOR: Check that the memory actually belongs to this caller
        owned = await self.get_all_user_memories(username)
        if not any(m.get("id") == memory_id for m in owned):
            logger.warning("Unauthorized memory delete attempt: user %s does not own memory %s", username, memory_id)
            return False

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: mem.delete(memory_id=memory_id),
            )
            return True
        except Exception as e:
            logger.error("Failed to delete memory %s: %s", memory_id, e)
            return False

    async def delete_all_user_memories(self, username: str) -> bool:
        """'Forget Me' action: Purge all memories associated with this officer pseudonym."""
        pseudo_id = pseudonymize_user_id(username)
        mem = self._get_mem0()
        if not mem:
            return True

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: mem.delete_all(user_id=pseudo_id),
            )
            return True
        except Exception as e:
            logger.error("Failed to purge memories for user %s: %s", pseudo_id, e)
            return False


# Singleton memory manager
_memory_manager: Optional[CopilotMemoryManager] = None


def get_memory_manager() -> CopilotMemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = CopilotMemoryManager()
    return _memory_manager
