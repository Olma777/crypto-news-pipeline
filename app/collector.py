"""RSS feed collector. Fetches and parses crypto news feeds."""

import hashlib
import logging
import re
from datetime import datetime, timezone, timedelta

import feedparser
import httpx
from dateutil import parser as dateutil_parser

from app.config import settings
from app.models import ArticleCandidate

logger = logging.getLogger(__name__)

# Shared client — created once, reused across calls
_http_client: httpx.AsyncClient | None = None


async def get_http_client() -> httpx.AsyncClient:
    """Get or create shared async HTTP client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={"User-Agent": "CryptoNewsPipeline/1.0"},
        )
    return _http_client


def normalize_title(title: str) -> str:
    """Normalize title for hashing: lowercase, strip punctuation and extra spaces."""
    title = title.lower().strip()
    title = re.sub(r"[^\w\s]", "", title)
    title = re.sub(r"\s+", " ", title)
    return title


def make_content_hash(title: str) -> str:
    """SHA-256 hash of normalized title for semantic dedup."""
    normalized = normalize_title(title)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_published_date(entry: dict) -> datetime | None:
    """Extract and parse published date from feed entry."""
    for field in ("published", "updated", "created"):
        raw = entry.get(field)
        if raw:
            try:
                dt = dateutil_parser.parse(raw)
                # Ensure timezone-aware (assume UTC if naive)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (ValueError, TypeError):
                continue
    return None


def extract_summary(entry: dict) -> str:
    """Extract summary/description from feed entry, strip HTML tags."""
    raw = entry.get("summary") or entry.get("description") or ""
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", raw)
    # Collapse whitespace
    clean = re.sub(r"\s+", " ", clean).strip()
    # Limit length
    if len(clean) > 1000:
        clean = clean[:1000] + "..."
    return clean


async def fetch_single_feed(
    feed_config: dict,
    max_age: timedelta,
) -> list[ArticleCandidate]:
    """Fetch and parse a single RSS feed. Returns list of candidates."""
    name = feed_config["name"]
    url = feed_config["url"]
    now = datetime.now(timezone.utc)
    cutoff = now - max_age
    articles: list[ArticleCandidate] = []

    try:
        client = await get_http_client()
        response = await client.get(url)
        response.raise_for_status()
        raw_content = response.text
    except httpx.TimeoutException:
        logger.warning(f"[{name}] Timeout fetching {url}")
        return []
    except httpx.HTTPStatusError as e:
        logger.warning(f"[{name}] HTTP {e.response.status_code} from {url}")
        return []
    except httpx.HTTPError as e:
        logger.warning(f"[{name}] HTTP error: {e}")
        return []

    try:
        feed = feedparser.parse(raw_content)
    except Exception as e:
        logger.warning(f"[{name}] Feed parse error: {e}")
        return []

    if feed.bozo and not feed.entries:
        logger.warning(f"[{name}] Malformed feed, 0 entries")
        return []

    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()

        if not title or not link:
            continue

        published = parse_published_date(entry)
        if published is None:
            # If no date, assume fresh (don't skip)
            published = now
        elif published < cutoff:
            continue

        summary = extract_summary(entry)
        content_hash = make_content_hash(title)

        articles.append(
            ArticleCandidate(
                source=name,
                source_url=link,
                title=title,
                summary=summary,
                published_at=published,
                content_hash=content_hash,
            )
        )

    logger.info(f"[{name}] Fetched {len(articles)} articles (from {len(feed.entries)} total)")
    return articles


async def collect_all_feeds() -> list[ArticleCandidate]:
    """
    Fetch all configured RSS feeds. One broken feed does NOT stop others.
    Returns combined list of ArticleCandidates sorted by published_at desc.
    """
    max_age = timedelta(hours=settings.max_article_age_h)
    all_articles: list[ArticleCandidate] = []
    errors: list[str] = []

    for feed_config in settings.rss_feeds:
        try:
            articles = await fetch_single_feed(feed_config, max_age)
            all_articles.extend(articles)
        except Exception as e:
            error_msg = f"[{feed_config['name']}] Unexpected error: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

    # Sort by published date, newest first
    all_articles.sort(key=lambda a: a.published_at, reverse=True)

    logger.info(
        f"Collector done: {len(all_articles)} articles from "
        f"{len(settings.rss_feeds)} feeds ({len(errors)} errors)"
    )
    return all_articles


async def close_http_client() -> None:
    """Close the shared HTTP client. Call on shutdown."""
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
