"""Execution engine and OpResult envelope for Nirdeshak Copilot."""

from eureka.copilot.execution.results import OpResult
from eureka.copilot.execution.executor import execute

__all__ = ["OpResult", "execute"]
