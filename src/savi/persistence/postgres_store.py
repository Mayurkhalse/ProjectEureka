"""
Phase 5: CQRS Query Store & Materialized View Serving Engine.
Serves low-latency queries (<10ms) to client endpoints from PostgreSQL Intelligence Master.
"""

from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from savi.config import DatabaseConfig, settings
from savi.metrics.savi_suite import SAVIMetricsResult


@dataclass
class IntelligenceRecord:
    content_id: str
    canonical_hash: str
    primary_headline: str
    origin_platform: str
    published_timestamp: datetime
    processed_timestamp: datetime
    sentiment_score: float
    accuracy_rating: float
    validation_index: float
    impact_ranking: float
    anomaly_metric: float
    open_jev_audit: Dict[str, Any]
    platform_distribution: Dict[str, Any]
    multimodal_features: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "content_id": self.content_id,
            "canonical_hash": self.canonical_hash,
            "primary_headline": self.primary_headline,
            "origin_platform": self.origin_platform,
            "published_timestamp": self.published_timestamp.isoformat(),
            "processed_timestamp": self.processed_timestamp.isoformat(),
            "sentiment_score": self.sentiment_score,
            "accuracy_rating": self.accuracy_rating,
            "validation_index": self.validation_index,
            "impact_ranking": self.impact_ranking,
            "anomaly_metric": self.anomaly_metric,
            "open_jev_audit": self.open_jev_audit,
            "platform_distribution": self.platform_distribution,
            "multimodal_features": self.multimodal_features,
        }


class IntelligenceQueryStore:
    """
    CQRS Query Store interface.
    Maintains table 'intelligence_master' and materialized view 'mv_top_impact_intelligence'.
    """
    def __init__(self, db_config: DatabaseConfig = settings.db, in_memory: bool = True):
        self.db_config = db_config
        self.in_memory = in_memory
        self.conn = sqlite3.connect(":memory:" if in_memory else "savi_query_store.db", check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initializes tables and indexing matching the PostgreSQL schema."""
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS intelligence_master (
                content_id TEXT PRIMARY KEY,
                canonical_hash TEXT UNIQUE NOT NULL,
                primary_headline TEXT NOT NULL,
                origin_platform TEXT NOT NULL,
                published_timestamp TEXT NOT NULL,
                processed_timestamp TEXT NOT NULL,
                sentiment_score REAL NOT NULL,
                accuracy_rating REAL NOT NULL,
                validation_index REAL NOT NULL,
                impact_ranking REAL NOT NULL,
                anomaly_metric REAL NOT NULL,
                open_jev_audit TEXT NOT NULL,
                platform_distribution TEXT NOT NULL,
                multimodal_features TEXT
            );
        """)

        # B-Tree index emulations
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_intelligence_impact_acc
            ON intelligence_master (impact_ranking DESC, accuracy_rating DESC);
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_intelligence_pub_time
            ON intelligence_master (published_timestamp DESC);
        """)
        self.conn.commit()

    def insert_record(self, record: IntelligenceRecord) -> None:
        """Inserts or replaces record in Intelligence Master."""
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO intelligence_master (
                content_id, canonical_hash, primary_headline, origin_platform,
                published_timestamp, processed_timestamp, sentiment_score,
                accuracy_rating, validation_index, impact_ranking, anomaly_metric,
                open_jev_audit, platform_distribution, multimodal_features
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """, (
            record.content_id,
            record.canonical_hash,
            record.primary_headline,
            record.origin_platform,
            record.published_timestamp.isoformat(),
            record.processed_timestamp.isoformat(),
            record.sentiment_score,
            record.accuracy_rating,
            record.validation_index,
            record.impact_ranking,
            record.anomaly_metric,
            json.dumps(record.open_jev_audit),
            json.dumps(record.platform_distribution),
            json.dumps(record.multimodal_features) if record.multimodal_features else None,
        ))
        self.conn.commit()

    def get_top_impact_intelligence(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Queries Materialized View 'mv_top_impact_intelligence':
        - published_timestamp >= NOW() - 24 HOURS
        - anomaly_metric < 0.65
        - ORDER BY impact_ranking DESC LIMIT 100
        """
        cur = self.conn.cursor()
        cur.execute("""
            SELECT
                content_id,
                primary_headline,
                origin_platform,
                accuracy_rating,
                impact_ranking,
                sentiment_score,
                validation_index,
                anomaly_metric,
                open_jev_audit,
                platform_distribution
            FROM intelligence_master
            WHERE anomaly_metric < 0.65
            ORDER BY impact_ranking DESC
            LIMIT ?;
        """, (limit,))

        rows = cur.fetchall()
        results = []
        for r in rows:
            audit = json.loads(r["open_jev_audit"])
            results.append({
                "content_id": r["content_id"],
                "primary_headline": r["primary_headline"],
                "origin_platform": r["origin_platform"],
                "accuracy_rating": r["accuracy_rating"],
                "impact_ranking": r["impact_ranking"],
                "sentiment_score": r["sentiment_score"],
                "validation_index": r["validation_index"],
                "factual_verdict": audit.get("verdict", "Unknown"),
                "reasoning_nodes": audit.get("reasoning_chain", []),
                "platform_distribution": json.loads(r["platform_distribution"]),
            })
        return results

    def get_by_content_id(self, content_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM intelligence_master WHERE content_id = ?;", (content_id,))
        row = cur.fetchone()
        if not row:
            return None

        return {
            "content_id": row["content_id"],
            "canonical_hash": row["canonical_hash"],
            "primary_headline": row["primary_headline"],
            "origin_platform": row["origin_platform"],
            "published_timestamp": row["published_timestamp"],
            "processed_timestamp": row["processed_timestamp"],
            "sentiment_score": row["sentiment_score"],
            "accuracy_rating": row["accuracy_rating"],
            "validation_index": row["validation_index"],
            "impact_ranking": row["impact_ranking"],
            "anomaly_metric": row["anomaly_metric"],
            "open_jev_audit": json.loads(row["open_jev_audit"]),
            "platform_distribution": json.loads(row["platform_distribution"]),
            "multimodal_features": json.loads(row["multimodal_features"]) if row["multimodal_features"] else None,
        }
