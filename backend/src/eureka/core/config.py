"""Configuration management for Project EUREKA using Pydantic Settings."""

from functools import lru_cache
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Production settings for Project EUREKA (DGIPR Maha-Command Center)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    ENVIRONMENT: str = Field(default="development", description="Runtime environment")
    DEBUG: bool = Field(default=False, description="Debug mode")
    PROJECT_NAME: str = Field(default="Project EUREKA", description="DGIPR Command Center Engine")

    # PostgreSQL 16
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="eureka_master")
    POSTGRES_USER: str = Field(default="eureka_user")
    POSTGRES_PASSWORD: str = Field(default="eureka_secure_2026")
    POSTGRES_POOL_SIZE: int = Field(default=20)
    POSTGRES_MAX_OVERFLOW: int = Field(default=10)
    POSTGRES_POOL_TIMEOUT: int = Field(default=30)

    # Neo4j 5.x
    NEO4J_URI: str = Field(default="bolt://localhost:7687")
    NEO4J_USER: str = Field(default="neo4j")
    NEO4J_PASSWORD: str = Field(default="eureka_graph_2026")
    NEO4J_MAX_CONNECTION_LIFETIME: int = Field(default=3600)
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = Field(default=50)

    # Redis & Celery
    REDIS_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/1")
    CELERY_TASK_ALWAYS_EAGER: bool = Field(default=False)

    # Security & RBAC (JWT)
    JWT_SECRET_KEY: str = Field(default="dgipr_maha_command_center_secret_2026_key")
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=480)  # 8 hours

    # WebAuthn (Face Lock / Biometrics - Zero biometric server storage)
    WEBAUTHN_RP_ID: str = Field(default="localhost", description="WebAuthn Relying Party ID")
    WEBAUTHN_RP_NAME: str = Field(default="DGIPR Command Center", description="WebAuthn RP Name")
    WEBAUTHN_ORIGIN: str = Field(default="http://localhost:3000", description="WebAuthn Origin")

    # Speech-to-Text Audio Transcription (Gemini API)
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Main Gemini API key for audio transcription")
    GEMINI_TRANSCRIBE_MODEL: str = Field(default="gemini-2.0-flash", description="Gemini transcription model")

    # Outbox Processor
    OUTBOX_POLL_INTERVAL_SECONDS: int = Field(default=5)
    OUTBOX_BATCH_SIZE: int = Field(default=100)
    OUTBOX_MAX_RETRIES: int = Field(default=5)

    # ML, NLP & Triton Inference
    MURIL_MODEL_ID: str = Field(default="google/muril-base-cased")
    SEMIF_OPENJEV_ENDPOINT: Optional[str] = Field(default=None)
    TRITON_SERVER_URL: str = Field(default="localhost:8001", description="Triton inference server gRPC endpoint")
    TRITON_ENABLED: bool = Field(default=True, description="Enable Triton gRPC inference offload")


    @property
    def async_database_url(self) -> str:
        """Construct PostgreSQL async connection URL for asyncpg."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def sync_database_url(self) -> str:
        """Construct PostgreSQL sync connection URL for psycopg2/alembic."""
        return (
            f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@"
            f"{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton getter for application settings."""
    return Settings()
