"""
Configuration module for SAVI (Sentiment, Accuracy, Validation, Impact) Platform.
Contains hyperparameter defaults, network topologies, and service settings.
"""

from typing import List
from pydantic import BaseModel, Field


class PPOConfig(BaseModel):
    """Hyperparameters for PPO Reinforcement Learning Scraper Controller."""
    # State dimension: [inter_request_delay, proxy_health, kappa_429, latency, dom_drift, quota_remaining]
    state_dim: int = 6
    action_dim: int = 6
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_epsilon: float = 0.20
    learning_rate: float = 0.0003
    value_coef: float = 0.50
    entropy_coef: float = 0.01
    epochs_per_update: int = 4
    batch_size: int = 32

    # Reward function weights: R_t = w1*V_valid - w2*E_429 - w3*(L_ms/1000) - w4*C_captcha - w5*I_ban
    # Hierarchy: w5 >> w2 > w4 >> w1 > w3
    w1_valid: float = 2.0
    w2_rate_limit: float = 15.0
    w3_latency: float = 0.5
    w4_captcha: float = 10.0
    w5_ban: float = 50.0

    # Step size for delay adjustments (ms)
    delta_t_ms: float = 250.0
    min_delay_ms: float = 50.0
    max_delay_ms: float = 10000.0
    soft_backoff_duration_s: float = 30.0


class IsolationRainforestConfig(BaseModel):
    """Hyperparameters for Extended Isolation Forest (Isolation Rainforest)."""
    n_trees: int = 100
    subsample_size: int = 256
    dimension: int = 6  # Engagement, account age, token perplexity, velocity gradient, etc.
    organic_threshold: float = 0.50
    flagged_threshold: float = 0.65  # [0.50, 0.65] = elevated review, > 0.65 = quarantine


class PipelineConfig(BaseModel):
    """Dynamic DAG Router & Orchestration settings."""
    macro_cascade_window_seconds: float = 900.0  # 15 minutes window for cross-platform grouping
    velocity_threshold: float = 1.5  # Acceleration threshold for macro routing
    batch_flush_interval_seconds: float = 5.0


class STGNNConfig(BaseModel):
    """Spatio-Temporal Graph Neural Network Configuration."""
    feature_dim: int = 32
    hidden_dim: int = 64
    temporal_kernel_size: int = 3
    num_st_blocks: int = 2
    dropout: float = 0.1


class SAVIMetricsConfig(BaseModel):
    """SAVI Analytical Suite hyperparameters."""
    sentiment_decay_lambda: float = 0.10  # Exponential decay for historic affective states
    base_authority_weight: float = 1.0


class DatabaseConfig(BaseModel):
    """Persistence and Graph Database configuration."""
    postgres_host: str = "localhost"
    postgres_port: int = 5433
    postgres_db: str = "savi_master"
    postgres_user: str = "savi_admin"
    postgres_password: str = "savi_secret"

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "savi_graph_secret"


class SAVIConfig(BaseModel):
    """Unified Platform Configuration."""
    ppo: PPOConfig = Field(default_factory=PPOConfig)
    rainforest: IsolationRainforestConfig = Field(default_factory=IsolationRainforestConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    stgnn: STGNNConfig = Field(default_factory=STGNNConfig)
    metrics: SAVIMetricsConfig = Field(default_factory=SAVIMetricsConfig)
    db: DatabaseConfig = Field(default_factory=DatabaseConfig)


# Default global settings instance
settings = SAVIConfig()
