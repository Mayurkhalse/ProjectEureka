"""Project EUREKA Open UI Copilot Package."""

from eureka.copilot.config import get_copilot_settings, get_copilot_health_status
from eureka.copilot.gemma_client import GemmaClient

__all__ = [
    "get_copilot_settings",
    "get_copilot_health_status",
    "GemmaClient",
]

