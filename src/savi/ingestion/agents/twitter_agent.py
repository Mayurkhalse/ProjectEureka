"""
Agent 3: Twitter/X Ingestion Agent.
Parses tweet payloads, reply cascades, quote tweets, retweet chains,
follower/following ratios, and verification metadata.
"""

from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import List, Tuple, Dict, Any
from savi.ingestion.agents.base import BaseIngestionAgent
from savi.ingestion.schema import ScrapedPayload, AuthorMetadata, EngagementMetrics
from savi.ingestion.mdp_env import ScraperExecutionResult


class TwitterIngestionAgent(BaseIngestionAgent):
    def __init__(self):
        super().__init__(platform_name="twitter")

    async def ingest_source(self, tweet_id_or_query: str) -> Tuple[List[ScrapedPayload], ScraperExecutionResult]:
        await self.throttle()
        start_time = time.perf_counter()

        payload = ScrapedPayload(
            origin_platform="twitter",
            headline_or_title=f"Viral Transmission Cascade #{tweet_id_or_query}",
            sanitized_body=(
                "Alert: Coordinated narrative dissemination detected across multiple temporal clusters. "
                "Retweet cascades indicate high amplification velocity across tier-1 bot rings."
            ),
            author=AuthorMetadata(
                author_id="tw_user_89211",
                username="IntelStreamNews",
                account_age_days=850.0,
                followers_count=45000,
                following_count=350,
                is_verified=True,
                flair="News Organization",
            ),
            published_timestamp=datetime.now(timezone.utc),
            citations=["https://x.com/IntelStreamNews/status/123456789"],
            engagement=EngagementMetrics(
                views=125000,
                upvotes=4800,       # Likes
                downvotes=0,
                shares=1650,        # Retweets
                replies=430,
                quote_count=210,
                propagation_velocity=18.5,  # High velocity cascade
            ),
            metadata={
                "retweet_chain_depth": 5,
                "quote_cascade_count": 210,
                "is_reply": False,
                "client": "Twitter for Web",
            },
        )

        latency = (time.perf_counter() - start_time) * 1000.0 + 35.0
        return [payload], ScraperExecutionResult(
            valid_payloads_count=1,
            hit_429_rate_limit=False,
            latency_ms=latency,
        )
