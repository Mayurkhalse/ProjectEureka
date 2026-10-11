"""
SAVI Platform: Full Autonomous End-to-End Simulation Runner.
Demonstrates the complete 5-phase segregated computational pipeline.
"""

import asyncio
import time
from datetime import datetime, timezone
from savi.api.main import SAVIPipelineOrchestrator
from savi.ingestion.schema import ScrapedPayload, AuthorMetadata, EngagementMetrics, MultimodalData


async def main():
    print("=" * 80)
    print("  SAVI (Sentiment, Accuracy, Validation, Impact) Intelligence Platform  ")
    print("  Autonomous Cross-Platform Harvesting, Verification & Serving Mesh    ")
    print("=" * 80)

    orchestrator = SAVIPipelineOrchestrator()
    await orchestrator.start()

    print("\n[Phase 1 & 2] Activating Quad-Scraper Mesh under Point-Based PPO Controller...")

    sources = [
        (orchestrator.web_agent, "https://reuters.com/markets/interest-rate-policy"),
        (orchestrator.reddit_agent, "economics"),
        (orchestrator.twitter_agent, "GlobalMarkets"),
        (orchestrator.youtube_agent, "macro_briefing_01"),
    ]

    for agent, target in sources:
        t0 = time.perf_counter()
        payloads, exec_res = await agent.ingest_source(target)
        harvest_ms = (time.perf_counter() - t0) * 1000.0

        print(f"\n---> Ingested from Agent [{agent.platform_name.upper()}]:")
        for p in payloads:
            print(f"     Title: {p.headline_or_title}")
            print(f"     Author: {p.author.username} (Age: {p.author.account_age_days}d, Verified: {p.author.is_verified})")
            print(f"     Engagement: {p.engagement.views} views, {p.engagement.shares} shares, velocity={p.engagement.propagation_velocity}/min")

            # PPO Controller decision step
            curr_state = orchestrator.mdp_env.state.to_normalized_vector()
            action, log_prob, val = orchestrator.ppo_controller.select_action(curr_state)
            next_state, reward, done, info = orchestrator.mdp_env.step(action, exec_res)
            orchestrator.ppo_controller.store_transition(curr_state, action, reward, val, log_prob, done)

            print(f"     [RL Controller] Action: {info.get('action')} | Feedback Reward R_t: {reward:.3f}")

            # End-to-End Pipeline Execution
            res = await orchestrator.ingest_and_process(p)
            print(f"     [DAG Router] Route: {res['route_type']}")
            print(f"     [Isolation Rainforest] Verdict: {res['anomaly_verdict']['action']} (Anomaly Score: {res['anomaly_verdict']['anomaly_score']:.4f})")
            print(f"     [Neo4j Staging] Triplets Extracted: {res['triplets_extracted']}")
            if res.get("open_jev"):
                print(f"     [Open JEV Engine] Verdict: {res['open_jev']['verdict']} (Entailment: {res['open_jev']['probabilities']['entailment']:.3f})")
            print(f"     [SAVI Metric Matrix]:")
            m = res["savi_metrics"]
            print(f"       * S (Sentiment Dynamics): {m['sentiment_score']:+.4f}")
            print(f"       * A (Factual Accuracy):  {m['accuracy_rating']:.4f}")
            print(f"       * V (Logical Validation): {m['validation_index']:.4f}")
            print(f"       * I (News Impact Index):  {m['impact_ranking']:.4f}")
            print(f"     [Processing Latency]: {res['pipeline_latency_ms']:.2f} ms")

    # PPO Policy Update
    ppo_update = orchestrator.ppo_controller.update(orchestrator.mdp_env.state.to_normalized_vector())
    print(f"\n[PPO Optimization] Policy updated across batch trajectory. Policy Loss: {ppo_update['policy_loss']:.4f}, Value Loss: {ppo_update['value_loss']:.4f}")

    print("\n" + "=" * 80)
    print("  [Phase 5: CQRS Serving] Querying PostgreSQL Materialized View (Target: <10ms)")
    print("=" * 80)

    t_query_start = time.perf_counter()
    top_intelligence = orchestrator.query_store.get_top_impact_intelligence(limit=10)
    query_latency_ms = (time.perf_counter() - t_query_start) * 1000.0

    print(f"\nRetrieved {len(top_intelligence)} top-impact intelligence items in {query_latency_ms:.3f} ms:")
    for idx, item in enumerate(top_intelligence, 1):
        print(f"  [{idx}] {item['primary_headline']}")
        print(f"      Platform: {item['origin_platform']} | Impact Rank: {item['impact_ranking']:.2f} | Accuracy: {item['accuracy_rating']:.2f} | Factual Verdict: {item['factual_verdict']}")
        print(f"      Reasoning: {item['reasoning_nodes'][0] if item.get('reasoning_nodes') else 'None'}")

    await orchestrator.stop()
    print("\nSimulation complete. Platform fully operational.")


if __name__ == "__main__":
    asyncio.run(main())
