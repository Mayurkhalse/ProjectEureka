"""Project EUREKA QUAD Ingestion Subsystem (Adapters and Connectors)."""

from eureka.quad_ingestion.base import BaseIngestionAdapter, compute_payload_hash
from eureka.quad_ingestion.csv_adapter import CSVAdapter
from eureka.quad_ingestion.api_connectors import GovApiConnector, PortalApiConnector
from eureka.quad_ingestion.crawl4ai_scraper import Crawl4AIScraperService

__all__ = [
    "BaseIngestionAdapter",
    "compute_payload_hash",
    "CSVAdapter",
    "GovApiConnector",
    "PortalApiConnector",
    "Crawl4AIScraperService",
]
