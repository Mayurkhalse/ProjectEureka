"""QUAD Ingestion: Crawl4AI Scraping Models for Lanes 3 and 4 (Web & Complex DOMs).

Integrates crawl4ai for navigating complex DOMs, bypassing bot-walls, extracting
markdown/text, and writing raw payloads directly into raw_events preserving provenance.
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from eureka.models.entities import RawEvent, SourceRegistry
from eureka.models.enums import SourceLane

logger = logging.getLogger(__name__)


def compute_payload_hash(content: str) -> str:
    """Compute SHA-256 hash of raw scraped content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class Crawl4AIScraperService:
    """Production scraping service integrating Crawl4AI for Lanes 3 and 4."""

    def __init__(self, timeout_sec: int = 45):
        self.timeout_sec = timeout_sec

    async def scrape_with_crawl4ai_async(
        self,
        url: str,
        css_selector: Optional[str] = None,
        js_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Asynchronously crawl a target URL using Crawl4AI."""
        try:
            from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

            config = CrawlerRunConfig(
                css_selector=css_selector,
                js_code=js_code,
                bypass_cache=True,
                verbose=False,
            )

            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(url=url, config=config)
                if result and result.success:
                    return {
                        "url": url,
                        "success": True,
                        "markdown": result.markdown or "",
                        "cleaned_html": result.cleaned_html or "",
                        "title": getattr(result, "metadata", {}).get("title", ""),
                        "links": getattr(result, "links", []),
                        "status_code": getattr(result, "status_code", 200),
                        "engine": "crawl4ai",
                    }
                else:
                    error_msg = getattr(result, "error_message", "Unknown crawl failure")
                    logger.warning("Crawl4AI arun returned non-success: %s", error_msg)
        except ImportError:
            logger.info("crawl4ai not installed or browser context unavailable; using resilient fallback")
        except Exception as exc:
            logger.warning("Crawl4AI exception for %s: %s; falling back to httpx engine", url, exc)

        # Resilient fallback using httpx
        return await self._fallback_scrape_async(url)

    async def _fallback_scrape_async(self, url: str) -> Dict[str, Any]:
        """High-resilience HTTP fallback client extracting text and title."""
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=self.timeout_sec, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            text = resp.text

            # Simple title extraction
            title = ""
            if "<title>" in text and "</title>" in text:
                title = text.split("<title>")[1].split("</title>")[0].strip()

            return {
                "url": url,
                "success": True,
                "markdown": text,
                "cleaned_html": text,
                "title": title,
                "links": [],
                "status_code": resp.status_code,
                "engine": "httpx_fallback",
            }

    def scrape_url_sync(
        self,
        url: str,
        css_selector: Optional[str] = None,
        js_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Synchronous wrapper to run async crawl4ai scraper."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(
                        asyncio.run,
                        self.scrape_with_crawl4ai_async(url, css_selector, js_code),
                    ).result()
            return loop.run_until_complete(
                self.scrape_with_crawl4ai_async(url, css_selector, js_code)
            )
        except RuntimeError:
            return asyncio.run(
                self.scrape_with_crawl4ai_async(url, css_selector, js_code)
            )

    def persist_raw_event(
        self,
        session: Session,
        ingestion_run_id: uuid.UUID,
        source: SourceRegistry,
        crawl_result: Dict[str, Any],
    ) -> RawEvent:
        """Write raw scraped content directly to raw_events table preserving provenance."""
        raw_content = crawl_result.get("markdown") or crawl_result.get("cleaned_html") or ""
        payload_hash = compute_payload_hash(raw_content)

        raw_event = RawEvent(
            id=uuid.uuid4(),
            ingestion_run_id=ingestion_run_id,
            source_id=source.id,
            lane=source.lane,
            payload_hash=payload_hash,
            raw_content=raw_content,
            raw_metadata={
                "url": crawl_result.get("url", source.base_url),
                "title": crawl_result.get("title", ""),
                "engine": crawl_result.get("engine", "crawl4ai"),
                "status_code": crawl_result.get("status_code", 200),
                "ingested_via": "Crawl4AIScraperService",
            },
            ingested_at=datetime.now(timezone.utc),
        )
        session.add(raw_event)
        session.flush()
        return raw_event

    def ingest_source(
        self,
        session: Session,
        source: SourceRegistry,
        ingestion_run_id: uuid.UUID,
    ) -> List[RawEvent]:
        """Scrape configured target URLs for Lane 3 or Lane 4 and persist raw events."""
        config = source.config_json or {}
        urls = config.get("urls", [source.base_url])
        css_selector = config.get("css_selector")
        js_code = config.get("js_code")

        logger.info(
            "Lane %s: Scraping source '%s' (%d URLs) via Crawl4AI",
            source.lane,
            source.name,
            len(urls),
        )

        raw_events: List[RawEvent] = []
        for url in urls:
            try:
                crawl_res = self.scrape_url_sync(url, css_selector, js_code)
                raw_event = self.persist_raw_event(session, ingestion_run_id, source, crawl_res)
                raw_events.append(raw_event)
            except Exception as exc:
                logger.error("Failed to scrape URL %s for source %s: %s", url, source.name, exc)

        logger.info("Lane %s: Ingested %d raw events from '%s'", source.lane, len(raw_events), source.name)
        return raw_events
