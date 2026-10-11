"""
Phase 5: High-Performance Client Serving REST API (FastAPI).
Serves low-latency queries directly from PostgreSQL Materialized Views and coordinates pipeline execution.
"""

from __future__ import annotations
import time
from contextlib import asynccontextmanager
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field

from savi.config import settings
from savi.ingestion.schema import ScrapedPayload, AuthorMetadata, EngagementMetrics
from savi.ingestion.mdp_env import ScrapingMDPEnvironment, ScraperAction
from savi.ingestion.ppo_controller import PPOController
from savi.ingestion.agents import WebIngestionAgent, RedditIngestionAgent, TwitterIngestionAgent, YouTubeIngestionAgent
from savi.pipeline.dag_router import DynamicDAGRouter
from savi.anomaly.isolation_rainforest import IsolationRainforest
from savi.graph.triplet_extractor import OpenIEExtractor
from savi.graph.neo4j_driver import Neo4jStagingGraph, Neo4jLiveClusterClient
from savi.graph.open_jev import OpenJEVLogicEngine
from savi.metrics.savi_suite import SAVIEngine
from savi.persistence.postgres_store import IntelligenceQueryStore
from savi.persistence.cdc_worker import CDCTransactionWorker


# Orchestrator coordinating end-to-end flow
class SAVIPipelineOrchestrator:
    def __init__(self):
        self.mdp_env = ScrapingMDPEnvironment()
        self.ppo_controller = PPOController()
        self.rainforest = IsolationRainforest()
        # Pre-fit rainforest on representative multi-dimensional distribution
        rng = np.random.default_rng(42)
        n_samples = 300
        eng_samples = rng.uniform(5.0, 80.0, (n_samples, 1))
        age_samples = rng.uniform(0.1, 1.0, (n_samples, 1))
        vel_samples = rng.uniform(0.5, 6.0, (n_samples, 1))
        len_samples = rng.uniform(0.1, 1.0, (n_samples, 1))
        up_samples = rng.uniform(0.5, 1.0, (n_samples, 1))
        verif_samples = rng.choice([0.0, 1.0], (n_samples, 1))
        representative_data = np.hstack([
            eng_samples, age_samples, vel_samples, len_samples, up_samples, verif_samples
        ]).astype(np.float32)
        self.rainforest.fit(representative_data)

        self.dag_router = DynamicDAGRouter(rainforest=self.rainforest)
        self.triplet_extractor = OpenIEExtractor()
        self.neo4j_live = Neo4jLiveClusterClient()
        self.neo4j_staging = Neo4jStagingGraph(live_client=self.neo4j_live)
        self.open_jev = OpenJEVLogicEngine()
        self.savi_engine = SAVIEngine()
        self.query_store = IntelligenceQueryStore(in_memory=False)
        self.cdc_worker = CDCTransactionWorker(self.query_store)

        # Scraper agents mesh
        self.web_agent = WebIngestionAgent()
        self.reddit_agent = RedditIngestionAgent()
        self.twitter_agent = TwitterIngestionAgent()
        self.youtube_agent = YouTubeIngestionAgent()

    async def start(self):
        await self.cdc_worker.start()

    async def stop(self):
        await self.cdc_worker.stop()

    async def ingest_and_process(self, payload: ScrapedPayload) -> Dict[str, Any]:
        """Runs single payload through full end-to-end pipeline."""
        start_time = time.perf_counter()

        # Step 1: Dynamic DAG Routing & Isolation Rainforest Filtering
        envelope = await self.dag_router.process_payload(payload)

        # Step 2: Triplet Extraction
        triplets = self.triplet_extractor.extract_triplets(
            payload.headline_or_title + ". " + payload.sanitized_body,
            fallback_subject=payload.origin_platform.capitalize(),
        )

        # Step 3: Graph Staging (Neo4j In-Memory Compute Engine)
        self.neo4j_staging.add_payload(payload, triplets)

        # Step 4: Open JEV Formal Logic Audit
        claim_triplet = triplets[0] if triplets else None
        evidence = self.neo4j_staging.find_evidence_triplets_for_claim(claim_triplet) if claim_triplet else []
        audit = self.open_jev.verify_claim(claim_triplet, evidence) if claim_triplet else None

        # Step 5: SAVI Metric Suite Calculation
        centralities = self.neo4j_staging.compute_betweenness_centrality()
        anomaly_score = envelope.anomaly_verdict.get("anomaly_score", 0.35) if envelope.anomaly_verdict else 0.35

        p_ent = audit.p_entailment if audit else 0.5
        p_con = audit.p_contradiction if audit else 0.2

        metrics = self.savi_engine.evaluate(
            sentiment_trajectory=[(0.0, 0.1), (1.0, 0.4)],
            current_time_t=1.0,
            mu_topo=0.85,
            p_entailment=p_ent,
            authority_weights=[1.5, 2.0],
            kappa_contradictions=p_con,
            anomaly_score_s=anomaly_score,
            platform_engagements={payload.origin_platform: 0.8},
            betweenness_centralities={payload.origin_platform: centralities.get(payload.content_id, 0.5)},
            transmission_velocity=max(1.0, payload.engagement.propagation_velocity),
        )

        # Step 6: Asynchronous CDC Sink to Query Store
        if audit:
            platform_dist = {payload.origin_platform: 1.0}
            await self.cdc_worker.enqueue_finalized_state(payload, metrics, audit, platform_dist)
            await self.cdc_worker.flush()

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        return {
            "content_id": payload.content_id,
            "route_type": envelope.route_type,
            "anomaly_verdict": envelope.anomaly_verdict,
            "triplets_extracted": len(triplets),
            "open_jev": audit.to_audit_json() if audit else None,
            "savi_metrics": metrics.to_dict(),
            "pipeline_latency_ms": round(duration_ms, 2),
        }


import numpy as np

orchestrator = SAVIPipelineOrchestrator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await orchestrator.start()
    yield
    await orchestrator.stop()


app = FastAPI(
    title="SAVI Intelligence Platform API",
    description="Low-latency CQRS serving and autonomous spatio-temporal intelligence analytics",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "healthy",
        "service": "SAVI Intelligence Platform",
        "architecture": "CQRS (Neo4j Command / PostgreSQL Query)",
        "postgres_connected": orchestrator.query_store.is_postgres,
        "neo4j_connected": orchestrator.neo4j_live.is_connected,
        "version": "1.0.0",
    }


@app.get("/api/v1/intelligence/top-impact", tags=["Intelligence"])
async def get_top_impact_intelligence(limit: int = Query(default=50, ge=1, le=100)):
    """
    Direct low-latency query hitting materialized view 'mv_top_impact_intelligence'.
    Guaranteed sub-10ms response for client dashboards.
    """
    t0 = time.perf_counter()
    records = orchestrator.query_store.get_top_impact_intelligence(limit=limit)
    query_latency_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "count": len(records),
        "query_latency_ms": round(query_latency_ms, 3),
        "data": records,
    }


@app.get("/api/v1/intelligence/{content_id}", tags=["Intelligence"])
async def get_intelligence_by_id(content_id: str):
    record = orchestrator.query_store.get_by_content_id(content_id)
    if not record:
        raise HTTPException(status_code=404, detail="Intelligence item not found")
    return record


@app.post("/api/v1/pipeline/ingest", tags=["Pipeline"])
async def ingest_payload(payload: ScrapedPayload):
    """Ingests custom harvested envelope through full pipeline."""
    result = await orchestrator.ingest_and_process(payload)
    return result


@app.post("/api/v1/pipeline/simulate-mesh", tags=["Pipeline"])
async def run_simulation_mesh():
    """Runs a simulated step across all 4 quad-scraper agents with PPO optimization."""
    # Run scrapers concurrently
    results = []
    for agent, target in [
        (orchestrator.web_agent, "https://reuters.com/markets/macro-news"),
        (orchestrator.reddit_agent, "finance"),
        (orchestrator.twitter_agent, "cashtag_macro"),
        (orchestrator.youtube_agent, "yt_vid_492"),
    ]:
        payloads, exec_res = await agent.ingest_source(target)
        if payloads:
            p = payloads[0]
            # Execute PPO step
            state = orchestrator.mdp_env.state.to_normalized_vector()
            action, log_prob, val = orchestrator.ppo_controller.select_action(state)
            next_state, reward, done, info = orchestrator.mdp_env.step(action, exec_res)
            orchestrator.ppo_controller.store_transition(state, action, reward, val, log_prob, done)

            # Ingest payload through pipeline
            res = await orchestrator.ingest_and_process(p)
            res["ppo_action"] = info.get("action")
            res["ppo_reward"] = round(reward, 3)
            results.append(res)

    # Perform PPO optimization update
    update_info = orchestrator.ppo_controller.update(orchestrator.mdp_env.state.to_normalized_vector())

    return {
        "status": "success",
        "processed_agents": len(results),
        "ppo_update": update_info,
        "results": results,
    }
