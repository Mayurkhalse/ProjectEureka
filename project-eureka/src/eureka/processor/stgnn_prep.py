"""Spatio-Temporal Graph Neural Network (StGNN) Data Preparation.

Extracts time-windowed node and edge features from Neo4j spatio-temporal projections
to format input tensors ready for graph neural network inference.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from eureka.core.neo4j_driver import Neo4jGraphService

logger = logging.getLogger(__name__)


class StGNNDataPreparation:
    """Extracts spatio-temporal graph snapshots from Neo4j."""

    @classmethod
    def extract_time_window_graph(
        cls,
        window_hours: int = 24,
        driver_service=Neo4jGraphService,
    ) -> Dict[str, Any]:
        """Extract nodes (District, Department, CanonicalEvent) and edges within time window."""
        cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        cutoff_iso = cutoff_dt.isoformat()

        # Extract active districts
        district_query = """
        MATCH (d:District)
        OPTIONAL MATCH (e:CanonicalEvent)-[:AFFECTS]->(d)
        WHERE e.last_updated_at >= $cutoff
        RETURN d.code AS code, d.name AS name, count(e) AS event_count
        """
        districts = driver_service.run_query(district_query, {"cutoff": cutoff_iso})

        # Extract department relations
        dept_query = """
        MATCH (dep:Department)
        OPTIONAL MATCH (e:CanonicalEvent)-[:RELATES_TO]->(dep)
        WHERE e.last_updated_at >= $cutoff
        RETURN dep.code AS code, dep.name AS name, count(e) AS event_count
        """
        departments = driver_service.run_query(dept_query, {"cutoff": cutoff_iso})

        # Extract spatio-temporal co-occurrence edges
        edge_query = """
        MATCH (d1:District)<-[:AFFECTS]-(e:CanonicalEvent)-[:AFFECTS]->(d2:District)
        WHERE d1.code < d2.code AND e.last_updated_at >= $cutoff
        RETURN d1.code AS source_district, d2.code AS target_district, count(e) AS weight
        """
        edges = driver_service.run_query(edge_query, {"cutoff": cutoff_iso})

        return {
            "window_hours": window_hours,
            "cutoff_timestamp": cutoff_iso,
            "nodes": {
                "districts": districts,
                "departments": departments,
            },
            "edges": edges,
            "features_summary": {
                "total_districts": len(districts),
                "total_departments": len(departments),
                "total_spatio_temporal_edges": len(edges),
            },
        }
