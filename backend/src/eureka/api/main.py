"""FastAPI application entry point for Project EUREKA."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from eureka.api.auth import create_access_token
from eureka.api.jobs_router import router as jobs_router
from eureka.api.reports_router import router as reports_router
from eureka.api.routers import conclusions, graph, health, hermes_router, quad, scoring
from eureka.core.config import get_settings
from eureka.core.neo4j_driver import Neo4jGraphService
from eureka.models.enums import UserRole

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""
    # Attempt Neo4j constraints initialization
    try:
        Neo4jGraphService.init_constraints()
    except Exception:
        pass
    yield
    # Shutdown
    Neo4jGraphService.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="The DGIPR Maha-Command Center Media Intelligence Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for secure command center dashboard access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DevTokenRequest(BaseModel):
    username: str
    role: UserRole
    district_code: Optional[str] = None


@app.post("/api/v1/auth/token", tags=["Auth & RBAC"])
async def generate_dev_token(payload: DevTokenRequest):
    """Generate signed JWT token for command center roles (Testing & Operator login)."""
    token = create_access_token(
        username=payload.username,
        role=payload.role,
        district_code=payload.district_code,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "username": payload.username,
        "role": payload.role,
        "district_code": payload.district_code,
    }


# Include all routers
from eureka.copilot.router import router as copilot_router
from eureka.api.routers.foundation_router import router as foundation_router
from eureka.api.routers.webauthn_router import router as webauthn_router

app.include_router(health.router)
app.include_router(quad.router)
app.include_router(conclusions.router)
app.include_router(scoring.router)
app.include_router(graph.router)
app.include_router(reports_router)
app.include_router(jobs_router)
app.include_router(hermes_router.router)
app.include_router(copilot_router)
app.include_router(foundation_router)
app.include_router(webauthn_router)

