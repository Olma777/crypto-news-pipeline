"""Deduplication engine. URL + content hash + ticker filter."""

import logging
import re
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import TICKER_NAMES, settings
from app.database import Article, ContentHash, async_session
from app.models import ArticleCandidate

logger = logging.getLogger(__name__)


def matches_watched_tickers(article: ArticleCandidate) -> list[str]:
    """
    Check if article mentions any watched ticker.
    Returns list of matched ticker symbols (e.g. ["BTC", "ETH"]).
    Matches both ticker symbols and full names, case-insensitive.
    """
    text = f"{article.title} {article.summary}".lower()
    matched: list[str] = []

    for ticker in settings.tickers_list:
        # Check ticker symbol (word boundary to avoid false matches like "LINK" in "linking")
        pattern = rf"\b{re.escape(ticker.lower())}\b"
        if re.search(pattern, text):
            matched.append(ticker)
            continue

        # Check full names from TICKER_NAMES mapping
        names = TICKER_NAMES.get(ticker, [])
        for name in names:
            if re.search(rf"\b{re.escape(name.lower())}\b", text):
                matched.append(ticker)
                break

    return matched


async def check_url_exists(session: AsyncSession, url: str) -> bool:
    """Check if article URL already exists in DB."""
    result = await session.execute(
        sa.select(sa.func.count()).where(Article.source_url == url)
    )
    return result.scalar_one() > 0


async def check_hash_exists(session: AsyncSession, content_hash: str) -> bool:
    """Check if content hash already exists (semantic dedup)."""
    result = await session.execute(
        sa.select(sa.func.count()).where(ContentHash.hash == content_hash)
    )
    return result.scalar_one() > 0


async def save_content_hash(session: AsyncSession, content_hash: str) -> None:
    """Save content hash to DB for future dedup. article_id linked later."""
    session.add(ContentHash(hash=content_hash))


async def filter_duplicates(
    candidates: list[ArticleCandidate],
) -> list[ArticleCandidate]:
    """
    Main dedup pipeline:
    1. Ticker filter — must mention at least one watched ticker
    2. URL dedup — skip if source_url already in articles table
    3. Content hash dedup — skip if normalized title hash exists

    Returns filtered list of new, relevant articles.
    Also saves new content hashes to DB for future runs.
    """
    if not candidates:
        return []

    new_articles: list[ArticleCandidate] = []
    stats = {"total": len(candidates), "no_ticker": 0, "url_dupe": 0, "hash_dupe": 0, "passed": 0}

    async with async_session() as session:
        for article in candidates:
            # Step 1: Ticker filter
            matched_tickers = matches_watched_tickers(article)
            if not matched_tickers:
                stats["no_ticker"] += 1
                continue

            # Step 2: URL dedup
            if await check_url_exists(session, article.source_url):
                stats["url_dupe"] += 1
                continue

            # Step 3: Content hash dedup
            if await check_hash_exists(session, article.content_hash):
                stats["hash_dupe"] += 1
                continue

            # Passed all filters — save hash and keep
            await save_content_hash(session, article.content_hash)
            new_articles.append(article)
            stats["passed"] += 1

        await session.commit()

    logger.info(
        f"Dedup: {stats['total']} candidates -> {stats['passed']} new "
        f"(no_ticker={stats['no_ticker']}, url_dupe={stats['url_dupe']}, "
        f"hash_dupe={stats['hash_dupe']})"
    )

    return new_articles


async def cleanup_old_hashes(max_age_hours: int = 24) -> int:
    """Remove content hashes older than max_age_hours. Run periodically."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)

    async with async_session() as session:
        result = await session.execute(
            sa.delete(ContentHash).where(ContentHash.created_at < cutoff)
        )
        await session.commit()
        deleted = result.rowcount if result.rowcount is not None else 0
        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old content hashes")
        return deleted
