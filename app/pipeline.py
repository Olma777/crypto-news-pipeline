"""Pipeline orchestrator. Chains: collect -> dedup -> score -> format -> post."""

import logging
import time
from datetime import datetime, timezone

import sqlalchemy as sa

from app.collector import collect_all_feeds
from app.database import Article, ContentHash, PipelineLog, async_session
from app.dedup import filter_duplicates
from app.models import ArticleCandidate, ScoringResult
from app.poster import post_articles
from app.scorer import score_articles

logger = logging.getLogger(__name__)


async def save_article_to_db(
    article: ArticleCandidate,
    score: ScoringResult,
    tg_message_id: int | None = None,
    status: str = "posted",
) -> int | None:
    """Save a scored article to the articles table. Returns article ID or None."""
    try:
        async with async_session() as session:
            db_article = Article(
                source=article.source,
                source_url=article.source_url,
                title_en=article.title,
                summary_en=article.summary,
                title_ru=score.title_ru,
                body_ru=score.body_ru,
                tickers=score.tickers,
                impact_score=score.impact_score,
                impact_reason=score.impact_reason,
                content_hash=article.content_hash,
                published_at=article.published_at,
                posted_at=datetime.now(timezone.utc) if status == "posted" else None,
                tg_message_id=tg_message_id,
                status=status,
            )
            session.add(db_article)
            await session.commit()
            await session.refresh(db_article)

            # Link content hash to article
            await session.execute(
                sa.update(ContentHash)
                .where(ContentHash.hash == article.content_hash)
                .values(article_id=db_article.id)
            )
            await session.commit()

            return db_article.id
    except Exception as e:
        logger.error(f"Failed to save article '{article.title[:50]}': {e}")
        return None


async def save_pipeline_log(
    fetched: int = 0,
    dupes: int = 0,
    scored: int = 0,
    posted: int = 0,
    errors: list[str] | None = None,
    duration_ms: int = 0,
) -> None:
    """Save pipeline run stats to pipeline_log table."""
    try:
        async with async_session() as session:
            log_entry = PipelineLog(
                source="all",
                fetched=fetched,
                dupes=dupes,
                scored=scored,
                posted=posted,
                errors=errors or [],
                duration_ms=duration_ms,
            )
            session.add(log_entry)
            await session.commit()
    except Exception as e:
        logger.error(f"Failed to save pipeline log: {e}")


async def run_pipeline() -> dict:
    """
    Main pipeline: collect -> dedup -> score -> post -> save.
    Returns stats dict. Never raises — all errors are caught and logged.
    """
    start = time.monotonic()
    stats = {
        "fetched": 0,
        "after_dedup": 0,
        "scored": 0,
        "posted": 0,
        "errors": [],
    }

    logger.info("=" * 50)
    logger.info("Pipeline run started")

    # Step 1: Collect
    try:
        candidates = await collect_all_feeds()
        stats["fetched"] = len(candidates)
        logger.info(f"Step 1 — Collected: {len(candidates)} articles")
    except Exception as e:
        error = f"Collect failed: {e}"
        logger.error(error)
        stats["errors"].append(error)
        candidates = []

    if not candidates:
        logger.info("No articles to process. Pipeline done.")
        duration_ms = int((time.monotonic() - start) * 1000)
        await save_pipeline_log(duration_ms=duration_ms, errors=stats["errors"])
        return stats

    # Step 2: Dedup + ticker filter
    try:
        new_articles = await filter_duplicates(candidates)
        stats["after_dedup"] = len(new_articles)
        logger.info(f"Step 2 — After dedup: {len(new_articles)} new articles")
    except Exception as e:
        error = f"Dedup failed: {e}"
        logger.error(error)
        stats["errors"].append(error)
        new_articles = []

    if not new_articles:
        logger.info("No new articles after dedup. Pipeline done.")
        duration_ms = int((time.monotonic() - start) * 1000)
        await save_pipeline_log(
            fetched=stats["fetched"],
            dupes=stats["fetched"],
            duration_ms=duration_ms,
            errors=stats["errors"],
        )
        return stats

    # Step 3: Score with Claude Sonnet
    try:
        scored = await score_articles(new_articles)
        stats["scored"] = len(scored)
        logger.info(f"Step 3 — Scored above threshold: {len(scored)} articles")
    except Exception as e:
        error = f"Scoring failed: {e}"
        logger.error(error)
        stats["errors"].append(error)
        scored = []

    if not scored:
        logger.info("No articles passed scoring threshold. Pipeline done.")
        duration_ms = int((time.monotonic() - start) * 1000)
        await save_pipeline_log(
            fetched=stats["fetched"],
            dupes=stats["fetched"] - stats["after_dedup"],
            scored=0,
            duration_ms=duration_ms,
            errors=stats["errors"],
        )
        return stats

    # Step 4: Post to Telegram
    try:
        posted = await post_articles(scored)
        stats["posted"] = len(posted)
        logger.info(f"Step 4 — Posted: {len(posted)} articles")
    except Exception as e:
        error = f"Posting failed: {e}"
        logger.error(error)
        stats["errors"].append(error)
        posted = []

    # Step 5: Save posted articles to DB
    for article, score, msg_id in posted:
        await save_article_to_db(article, score, tg_message_id=msg_id, status="posted")

    # Save scored-but-not-posted (posted failed) articles too
    posted_urls = {a.source_url for a, _, _ in posted}
    for article, score in scored:
        if article.source_url not in posted_urls:
            await save_article_to_db(article, score, status="error")

    # Log pipeline run
    duration_ms = int((time.monotonic() - start) * 1000)
    await save_pipeline_log(
        fetched=stats["fetched"],
        dupes=stats["fetched"] - stats["after_dedup"],
        scored=stats["scored"],
        posted=stats["posted"],
        duration_ms=duration_ms,
        errors=stats["errors"],
    )

    logger.info(
        f"Pipeline done in {duration_ms}ms: "
        f"fetched={stats['fetched']}, deduped={stats['after_dedup']}, "
        f"scored={stats['scored']}, posted={stats['posted']}"
    )
    logger.info("=" * 50)

    return stats
