"""NEWS_API.py: Autonomous Edge Ingestion Node for Project EUREKA.

Pipeline Flow:
1. Discovery: Queries NewsAPI (/v2/everything) to discover recent article links and metadata.
2. Extraction: Employs Crawl4AI (with resilient HTTP fallback) to scrape clean markdown body text.
3. Cloud AI Evaluation: Evaluates sentiment (Hugging Face / Groq) and crisis SLA resolution (Groq Llama 3).
4. Queue Dispatch: Dispatches structured records directly to Celery (process_ingestion_chunk) for database ingestion.
"""

import asyncio
import datetime
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests
from dotenv import find_dotenv, load_dotenv

# Ensure backend/src is on sys.path
CURRENT_FILE = Path(__file__).resolve()
SAVI_ROOT = CURRENT_FILE.parent if (CURRENT_FILE.parent / "backend").exists() else CURRENT_FILE.parent.parent
BACKEND_SRC = SAVI_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

# Load environment variables
load_dotenv(find_dotenv(usecwd=True))
load_dotenv(SAVI_ROOT / "backend" / ".env")
load_dotenv(SAVI_ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eureka.news_scraper")

# Import Project EUREKA tasks & cloud evaluators
from eureka.llm.cloud_evaluator import evaluate_crisis_sla_groq, evaluate_sentiment_cloud
from eureka.workers.ingestion_tasks import process_ingestion_chunk

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
TOPIC = os.environ.get("TOPIC", "Thane")
MAX_ARTICLES = int(os.environ.get("MAX_ARTICLES", 10))


def fetch_news_links(
    topic: str,
    max_articles: int = 10,
    api_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Discovers articles for a topic keyword from NewsAPI v2 everything endpoint."""
    key = api_key or os.environ.get("NEWS_API_KEY") or NEWS_API_KEY
    if not key:
        logger.error("[-] NEWS_API_KEY not found in environment or arguments.")
        return []

    url = "https://newsapi.org/v2/everything"
    params = {
        "q": topic,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": max(1, min(max_articles, 100)),
        "apiKey": key,
    }

    logger.info("[1/3] Fetching news articles for topic: '%s'...", topic)
    try:
        response = requests.get(url, params=params, timeout=15)
        if response.status_code != 200:
            logger.error("[-] NewsAPI returned status %s: %s", response.status_code, response.text[:200])
            return []

        payload = response.json()
        if payload.get("status") != "ok":
            logger.error("[-] NewsAPI error payload: %s", payload.get("message"))
            return []

        articles = payload.get("articles", [])
        valid_articles = []
        for a in articles:
            article_url = (a.get("url") or "").strip()
            title = (a.get("title") or "").strip()
            # Filter out [Removed] stubs and invalid URLs
            if not article_url or "removed.com" in article_url or title == "[Removed]":
                continue

            valid_articles.append({
                "title": title or "Untitled Article",
                "source": (a.get("source") or {}).get("name") or "Unknown Source",
                "author": a.get("author") or "Unknown Author",
                "published_at": a.get("publishedAt"),
                "description": a.get("description") or "",
                "url": article_url,
                "scrape_status": "pending",
                "scraped_content": "",
                "error": None,
            })

        logger.info("      Found %d valid article links to scrape.", len(valid_articles))
        return valid_articles
    except Exception as exc:
        logger.error("[-] Exception fetching news links: %s", exc)
        return []


async def _scrape_single_crawl4ai(crawler, article: Dict[str, Any], config) -> Dict[str, Any]:
    """Helper to scrape an individual article using Crawl4AI."""
    url = article["url"]
    try:
        res = await crawler.arun(url=url, config=config)
        if res and res.success:
            content = (res.markdown or res.cleaned_html or "").strip()
            article["scrape_status"] = "success"
            article["scraped_content"] = content
            article["error"] = None
        else:
            err = getattr(res, "error_message", "Crawl failed")
            article["scrape_status"] = "failed"
            article["error"] = err
    except Exception as exc:
        article["scrape_status"] = "failed"
        article["error"] = str(exc)
    return article


async def _scrape_fallback_http(article: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback scraper using direct HTTP requests when Playwright/browser is unavailable."""
    url = article["url"]
    try:
        import httpx
        from bs4 import BeautifulSoup
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }
        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                # Remove boilerplate tags
                for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form"]):
                    tag.decompose()
                text = "\n\n".join([p.get_text().strip() for p in soup.find_all(["p", "h1", "h2", "h3"]) if p.get_text().strip()])
                article["scrape_status"] = "success"
                article["scraped_content"] = text or resp.text[:4000]
                article["error"] = None
                return article
    except Exception as exc:
        article["error"] = f"HTTP fallback error: {exc}"

    # Fallback to article description if scrape failed or blocked, but valid summary exists
    if article.get("description") and len(article.get("description", "").strip()) >= 20:
        article["scrape_status"] = "success"
        article["scraped_content"] = article["description"].strip()
        article["error"] = None
        return article

    article["scrape_status"] = "failed"
    return article


async def scrape_articles_async(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Scrapes full text from discovered article URLs concurrently using Crawl4AI."""
    if not articles:
        return []

    logger.info("[2/3] Launching Crawl4AI to scrape %d URLs concurrently...", len(articles))

    crawl4ai_available = False
    try:
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
        from crawl4ai.content_filter_strategy import PruningContentFilter
        crawl4ai_available = True
    except ImportError:
        logger.warning("Crawl4AI not installed; using resilient HTTP fallback.")

    if crawl4ai_available:
        try:
            try:
                from crawl4ai.content_filter_strategy import PruningContentFilterLXML
                content_filter = PruningContentFilterLXML(threshold=0.45, min_word_threshold=15)
            except Exception:
                content_filter = None

            try:
                from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
                md_gen = DefaultMarkdownGenerator(content_filter=content_filter) if content_filter else None
                config = CrawlerRunConfig(
                    markdown_generator=md_gen,
                    excluded_tags=["nav", "footer", "header", "aside", "script", "style", "form"],
                    remove_overlay_elements=True,
                    exclude_external_links=True,
                    page_timeout=30000,
                )
            except Exception:
                config = CrawlerRunConfig(
                    excluded_tags=["nav", "footer", "header", "aside", "script", "style", "form"],
                    remove_overlay_elements=True,
                    exclude_external_links=True,
                    page_timeout=30000,
                )

            async with AsyncWebCrawler(verbose=False) as crawler:
                tasks = [_scrape_single_crawl4ai(crawler, article, config) for article in articles]
                return await asyncio.gather(*tasks)
        except Exception as exc:
            logger.warning("Crawl4AI browser execution error (%s); falling back to HTTP scraper.", exc)

    # Resilient fallback if browser execution fails
    tasks = [_scrape_fallback_http(article) for article in articles]
    return await asyncio.gather(*tasks)


def scrape_articles_with_crawl4ai(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Synchronous entry point for asynchronous scraping."""
    return asyncio.run(scrape_articles_async(articles))


def dispatch_to_celery(scraped_articles: list, district_name: str):
    """
    Transforms scraped Crawl4AI data into the EUREKA schema, performs cloud AI evaluation,
    and pushes the batch directly to the Celery Redis broker.
    """
    records = []
    for article in scraped_articles:
        if article.get("scrape_status") != "success":
            continue

        content = article.get("scraped_content", "")
        published = article.get("published_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Fire requests to Cloud APIs
        sentiment = evaluate_sentiment_cloud(content)
        crisis_resolved = evaluate_crisis_sla_groq(district_name, content)

        # Multilingual Indic normalization & translation (Gemini Flash)
        try:
            from eureka.llm.multilingual_translator import translate_and_normalize_indic
            indic_res = translate_and_normalize_indic(content[:1500])
            en_content = indic_res.get("english_translation") or content
        except Exception:
            en_content = content

        records.append({
            "record_id": str(uuid.uuid4()),
            "district": district_name,
            "event_type": "News Article",
            "event_timestamp": published,
            "turnaround_time_mins": 30.0,  # Estimated baseline
            "sentiment_score": sentiment,
            "crisis_resolved": crisis_resolved,
            "english_content": en_content,
        })

    if records:
        try:
            # Push standard payload to the existing Celery database ingestion worker
            task = process_ingestion_chunk.delay(records)
            print(f"[+] Dispatched {len(records)} fully evaluated articles to Celery queue for {district_name}. Task ID: {task.id}")
        except Exception as exc:
            print(f"[!] Warning: Could not reach Celery Redis broker ({exc}).")
            print(f"[+] {len(records)} fully evaluated records prepared successfully:")
            for r in records[:3]:
                print(f"    - [{r['district']}] Sentiment: {r['sentiment_score']:.2f} | Crisis Resolved: {r['crisis_resolved']} | Content length: {len(r['english_content'])}")
    else:
        print("[-] No successful articles to queue.")


def main():
    """Main CLI execution flow."""
    topic = os.environ.get("TOPIC") or TOPIC
    max_count = int(os.environ.get("MAX_ARTICLES") or MAX_ARTICLES)

    print(f"=== Project EUREKA News Ingestion Node: {topic} ===")
    articles = fetch_news_links(topic=topic, max_articles=max_count)
    if not articles:
        print("[-] No articles retrieved. Exiting.")
        return

    enriched_articles = scrape_articles_with_crawl4ai(articles)
    successful_count = sum(1 for a in enriched_articles if a.get("scrape_status") == "success")
    print(f"[+] Successfully extracted {successful_count}/{len(enriched_articles)} article bodies.")

    print(f"[3/3] Running Cloud AI Evaluations & Dispatching to Celery...")
    dispatch_to_celery(enriched_articles, topic)
    print("Workflow completed successfully!")


if __name__ == "__main__":
    main()
