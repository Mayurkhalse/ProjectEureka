"""Strict IPCS (Integrated Public Communication System) Adapter.

Per DGIPR architectural specification:
Since the exact logic is pending DGIPR definition, it returns {"status": "not_configured"}.
No speculative or hallucinated IPCS functionality is allowed.
"""

from typing import Any, Dict


class IPCSAdapter:
    """Strict interface adapter for DGIPR IPCS."""

    @classmethod
    def dispatch_release(cls, *args, **kwargs) -> Dict[str, Any]:
        """Dispatch a press release via IPCS. Returns not_configured status."""
        return {"status": "not_configured"}

    @classmethod
    def sync_feedback(cls, *args, **kwargs) -> Dict[str, Any]:
        """Sync feedback from IPCS. Returns not_configured status."""
        return {"status": "not_configured"}

    @classmethod
    def get_status(cls) -> Dict[str, Any]:
        """Retrieve IPCS interface status."""
        return {"status": "not_configured"}
