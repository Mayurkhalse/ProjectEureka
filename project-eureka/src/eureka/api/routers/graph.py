"""Graph Projection and IPCS interface endpoints."""

from fastapi import APIRouter, Depends
from eureka.api.auth import TokenData, require_roles
from eureka.models.enums import UserRole
from eureka.processor.ipcs_adapter import IPCSAdapter
from eureka.processor.stgnn_prep import StGNNDataPreparation

router = APIRouter(prefix="/api/v1", tags=["Graph & IPCS"])


@router.get("/graph/spatio-temporal")
async def get_spatio_temporal_graph(
    window_hours: int = 24,
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DISTRICT_COLLECTOR])),
):
    """Retrieve time-windowed spatio-temporal graph projections from Neo4j for StGNN."""
    return StGNNDataPreparation.extract_time_window_graph(window_hours=window_hours)


@router.get("/ipcs/status")
async def get_ipcs_status(
    user: TokenData = Depends(require_roles([UserRole.DG_STATE_ADMIN, UserRole.DIO_DESK])),
):
    """Query strict IPCS interface status (returns not_configured per DGIPR specification)."""
    return IPCSAdapter.get_status()
