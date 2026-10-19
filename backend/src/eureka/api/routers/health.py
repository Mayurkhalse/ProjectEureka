"""Health check and readiness endpoints for Project EUREKA."""

from fastapi import APIRouter
from eureka.core.database import check_async_db_health
from eureka.core.neo4j_driver import Neo4jGraphService

router = APIRouter(tags=["Health & Telemetry"])


@router.get("/health")
@router.get("/api/v1/health")
async def health_check():
    """Verify operational status of all backend subsystems."""
    from eureka.copilot.config import get_copilot_health_status

    pg_ok = await check_async_db_health()
    neo_ok = Neo4jGraphService.check_health()
    copilot_status = get_copilot_health_status()

    status = "healthy" if (pg_ok and neo_ok) else "degraded"
    return {
        "status": status,
        "engine": "Project EUREKA (DGIPR Maha-Command Center)",
        "subsystems": {
            "postgresql_16": "online" if pg_ok else "unreachable",
            "neo4j_graph": "online" if neo_ok else "unreachable",
            "open_ui_copilot": copilot_status,
        },
    }

