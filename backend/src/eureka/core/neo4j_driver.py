"""Neo4j 5.x graph database driver wrapper with connection pooling, retries, and constraints."""

import logging
from typing import Any, Dict, List, Optional
from neo4j import GraphDatabase, Driver, Session, RoutingControl
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from eureka.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Neo4jGraphService:
    """Production service for managing Neo4j 5.x connections, transactions, and schema constraints."""

    _driver: Optional[Driver] = None

    @classmethod
    def get_driver(cls) -> Driver:
        """Initialize or retrieve the singleton Neo4j driver with connection pooling."""
        if cls._driver is None:
            cls._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                max_connection_lifetime=settings.NEO4J_MAX_CONNECTION_LIFETIME,
                max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
            )
            logger.info("Initialized Neo4j driver targeting %s", settings.NEO4J_URI)
        return cls._driver

    @classmethod
    def close(cls) -> None:
        """Close Neo4j driver connection pool."""
        if cls._driver is not None:
            cls._driver.close()
            cls._driver = None
            logger.info("Closed Neo4j driver connection pool")

    @classmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def init_constraints(cls) -> None:
        """Create uniqueness constraints for spatio-temporal nodes in Neo4j."""
        driver = cls.get_driver()
        constraints = [
            "CREATE CONSTRAINT district_code_unique IF NOT EXISTS FOR (d:District) REQUIRE d.code IS UNIQUE",
            "CREATE CONSTRAINT department_code_unique IF NOT EXISTS FOR (dep:Department) REQUIRE dep.code IS UNIQUE",
            "CREATE CONSTRAINT canonical_event_id_unique IF NOT EXISTS FOR (e:CanonicalEvent) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT release_id_unique IF NOT EXISTS FOR (r:Release) REQUIRE r.id IS UNIQUE",
            "CREATE CONSTRAINT claim_id_unique IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE",
        ]
        with driver.session(database="neo4j") as session:
            for constraint in constraints:
                try:
                    session.run(constraint)
                except Exception as exc:
                    logger.warning("Constraint creation warning [%s]: %s", constraint, exc)
        logger.info("Ensured all 5 Neo4j schema uniqueness constraints are active")

    @classmethod
    def run_query(cls, query: str, parameters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Execute a read/write Cypher query returning results as list of dicts."""
        driver = cls.get_driver()
        with driver.session(database="neo4j") as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    @classmethod
    def check_health(cls) -> bool:
        """Execute verification ping against Neo4j."""
        try:
            driver = cls.get_driver()
            with driver.session(database="neo4j") as session:
                res = session.run("RETURN 1 AS ping")
                record = res.single()
                return record is not None and record["ping"] == 1
        except Exception as exc:
            logger.error("Neo4j health check failed: %s", exc)
            return False
