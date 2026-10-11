-- SAVI Platform: Intelligence Master Schema & Materialized Views (PostgreSQL 16)

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Core Table: Platform Intelligence Master
CREATE TABLE IF NOT EXISTS intelligence_master (
    content_id UUID PRIMARY KEY,
    canonical_hash VARCHAR(64) UNIQUE NOT NULL,
    primary_headline TEXT NOT NULL,
    origin_platform VARCHAR(16) NOT NULL,
    published_timestamp TIMESTAMPTZ NOT NULL,
    processed_timestamp TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    
    -- Structured Metric Columns for Fast B-Tree Indexing
    sentiment_score REAL NOT NULL,
    accuracy_rating REAL NOT NULL,
    validation_index REAL NOT NULL,
    impact_ranking REAL NOT NULL,
    anomaly_metric REAL NOT NULL,

    -- Unstructured & Complex Reasoning Engines stored in JSONB
    open_jev_audit JSONB NOT NULL,
    platform_distribution JSONB NOT NULL,
    multimodal_features JSONB
);

-- Indices for Low-Latency Query Execution
CREATE INDEX IF NOT EXISTS idx_intelligence_impact_acc 
ON intelligence_master (impact_ranking DESC, accuracy_rating DESC);

CREATE INDEX IF NOT EXISTS idx_intelligence_pub_time 
ON intelligence_master (published_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_open_jev_audit_gin 
ON intelligence_master USING GIN (open_jev_audit);

-- Materialized View for Real-Time Client Dashboards
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_top_impact_intelligence AS
SELECT 
    content_id,
    primary_headline,
    origin_platform,
    accuracy_rating,
    impact_ranking,
    open_jev_audit->>'verdict' AS factual_verdict,
    open_jev_audit->'reasoning_chain' AS reasoning_nodes,
    platform_distribution
FROM intelligence_master
WHERE published_timestamp >= NOW() - INTERVAL '24 HOURS'
  AND anomaly_metric < 0.65
ORDER BY impact_ranking DESC
LIMIT 100;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_content_id ON mv_top_impact_intelligence (content_id);
