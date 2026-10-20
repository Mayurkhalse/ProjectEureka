"""Open UI Copilot Configuration & Key Isolation Layer.

MANDATORY ISOLATION RULE:
Only eureka/copilot/ may read OPENUI_COPILOT_GEMINI_API_KEY and THESYS_API_KEY.
No other module in the codebase may inspect or reference these environment variables.
"""

import os
from functools import lru_cache
from typing import Optional, Dict, Any
from pydantic import Field, AliasChoices
from pydantic_settings import BaseSettings, SettingsConfigDict


class CopilotSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    COPILOT_ENABLED: bool = Field(default=False, description="Master feature toggle for Open UI Copilot")
    COPILOT_UI_ENGINE: str = Field(
        default="deterministic",
        description="Generative UI engine: 'deterministic' (ViewSpec) or 'c1' (Thesys C1)",
    )
    COPILOT_MODEL: str = Field(
        default="models/gemma-4-26b-a4b-it",
        validation_alias=AliasChoices("COPILOT_MODEL", "GEMMA_MODEL_ID"),
        description="Google Gemma model identifier"
    )
    C1_MODEL_ID: str = Field(
        default="c1-20250416",
        description="Thesys C1 model ID (verified stable)",
    )
    C1_BASE_URL: str = Field(
        default="https://api.thesys.dev/v1/embed",
        description="Thesys C1 OpenAI-compatible endpoint",
    )
    COPILOT_EMBED_MODEL: str = Field(default="thesys-embed", description="Thesys embedding model identifier")
    COPILOT_MEMORY_ENABLED: bool = Field(default=False, description="Enable Mem0 long-term user memory")
    
    QDRANT_URL: str = Field(default="http://localhost:6333", description="Qdrant vector store endpoint")
    QDRANT_API_KEY: Optional[str] = Field(default=None, description="Qdrant API key if secured")
    
    # Isolated keys - only read within eureka/copilot/
    OPENUI_COPILOT_GEMINI_API_KEY: Optional[str] = Field(
        default=None,
        description="Google AI Studio API key dedicated for Open UI Copilot",
    )
    THESYS_API_KEY: Optional[str] = Field(
        default=None,
        description="Thesys API key for OpenAI-compatible embedding service",
    )
    
    COPILOT_KILL_SWITCH: bool = Field(default=False, description="Emergency kill switch to halt copilot queries")
    COPILOT_RATE_LIMIT_USER_PER_MIN: int = Field(default=10, description="Per-user query rate cap per minute")
    COPILOT_RATE_LIMIT_GLOBAL_PER_MIN: int = Field(default=60, description="Global copilot query rate cap per minute")
    COPILOT_MAX_OUTPUT_TOKENS: int = Field(default=4096, description="Maximum token cap per model generation")
    COPILOT_TIMEOUT_SECONDS: float = Field(default=25.0, description="Network timeout for LLM calls")
    COPILOT_MEMORY_TIMEOUT_MS: int = Field(default=800, description="Fail-open search timeout for Mem0")
    COPILOT_MEMORY_TTL_DAYS: int = Field(default=90, description="Retention TTL for user presentation preferences")
    COPILOT_SECRET_SALT: str = Field(
        default="eureka_copilot_pseudonymization_salt_2026",
        description="Salt for user ID HMAC pseudonymization",
    )

    def get_effective_gemini_key(self) -> Optional[str]:
        """Return the copilot Gemini key, isolated strictly to copilot and dev studio keys."""
        key = self.OPENUI_COPILOT_GEMINI_API_KEY or os.getenv("GOOGLE_STUDIO_API_KEY")
        if key and key.strip():
            return key.strip()
        return None


@lru_cache(maxsize=1)
def get_copilot_settings() -> CopilotSettings:
    """Cached singleton for copilot settings."""
    return CopilotSettings()


def get_copilot_health_status() -> Dict[str, Any]:
    """Report copilot status (ok / degraded / disabled) WITHOUT calling the model."""
    settings = get_copilot_settings()
    
    if not settings.COPILOT_ENABLED:
        return {
            "status": "disabled",
            "model": settings.COPILOT_MODEL,
            "memory_enabled": False,
            "reason": "COPILOT_ENABLED is false",
        }
    
    if settings.COPILOT_KILL_SWITCH:
        return {
            "status": "degraded",
            "model": settings.COPILOT_MODEL,
            "memory_enabled": settings.COPILOT_MEMORY_ENABLED,
            "reason": "Emergency kill switch active",
        }
    
    key = settings.get_effective_gemini_key()
    if not key:
        return {
            "status": "degraded",
            "model": settings.COPILOT_MODEL,
            "memory_enabled": settings.COPILOT_MEMORY_ENABLED,
            "reason": "OPENUI_COPILOT_GEMINI_API_KEY is not configured",
        }
        
    if settings.COPILOT_MEMORY_ENABLED and not settings.THESYS_API_KEY:
        return {
            "status": "degraded",
            "model": settings.COPILOT_MODEL,
            "memory_enabled": False,
            "reason": "Memory enabled but THESYS_API_KEY is not configured",
        }
        
    return {
        "status": "ok",
        "model": settings.COPILOT_MODEL,
        "embed_model": settings.COPILOT_EMBED_MODEL,
        "memory_enabled": settings.COPILOT_MEMORY_ENABLED,
    }
