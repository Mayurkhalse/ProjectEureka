"""OpResult envelope model and canonical hashing for telemetry and audit.

Every executed tool operation produces an OpResult envelope tagging data quality,
execution duration, source status, and a canonical SHA-256 payload hash.
"""

import hashlib
import json
import time
from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, ConfigDict


DataQuality = Literal[
    "live",
    "seed",
    "synthetic",
    "heuristic",
    "pipeline_memory",
    "partial",
]

ResultStatus = Literal["ok", "error", "timeout", "policy_drift"]


class OpResult(BaseModel):
    """Execution outcome envelope for an individual authorized operation."""
    model_config = ConfigDict(extra="forbid", frozen=True)

    op_id: str
    group: str
    tool: str
    args: Dict[str, Any]
    status: ResultStatus
    data: Optional[Any] = None
    as_of: Optional[str] = None
    source_status: Optional[str] = None
    data_quality: DataQuality
    duration_ms: int
    result_hash: Optional[str] = None

    @classmethod
    def ok(
        cls,
        authorized_op: Any,
        data: Any,
        start_time_monotonic: float,
        data_quality: DataQuality = "live",
    ) -> "OpResult":
        duration = int((time.monotonic() - start_time_monotonic) * 1000)
        as_of = None
        source_status = None
        if isinstance(data, dict):
            as_of = data.get("as_of")
            source_status = data.get("source_status")

        # Canonical JSON sha256 hash for audit (payload itself is not stored in audit)
        res_hash = None
        if data is not None:
            try:
                canonical_str = json.dumps(data, sort_keys=True, default=str)
                res_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()
            except Exception:
                res_hash = None

        return cls(
            op_id=authorized_op.op.op_id,
            group=authorized_op.op.group,
            tool=authorized_op.op.tool,
            args=authorized_op.op.args,
            status="ok",
            data=data,
            as_of=as_of,
            source_status=source_status,
            data_quality=data_quality,
            duration_ms=duration,
            result_hash=res_hash,
        )

    @classmethod
    def failed(
        cls,
        authorized_op: Any,
        status: ResultStatus,
        start_time_monotonic: float,
    ) -> "OpResult":
        duration = int((time.monotonic() - start_time_monotonic) * 1000)
        return cls(
            op_id=authorized_op.op.op_id,
            group=authorized_op.op.group,
            tool=authorized_op.op.tool,
            args=authorized_op.op.args,
            status=status,
            data=None,
            as_of=None,
            source_status="unavailable",
            data_quality="live",
            duration_ms=duration,
            result_hash=None,
        )
