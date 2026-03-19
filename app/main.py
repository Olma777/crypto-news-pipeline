"""FastAPI app with APScheduler. Entry point for the service."""

import logging
from contextlib import asynccontextmanager

import sqlalchemy as sa
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI

from app.collector import close_http_client
from app.config import settings
from app.database import Article, PipelineLog, async_session, engine
from app.dedup import cleanup_old_hashes
from app.pipeline import run_pipeline
from app.poster import close_bot

# Logging setup
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Scheduler - module level so it works under uvicorn
scheduler = AsyncIOScheduler()


async def scheduled_pipeline_run():
    """Wrapper for scheduled pipeline execution."""
    try:
        logger.info("Scheduled pipeline run triggered")
        stats = await run_pipeline()
        logger.info(f"Scheduled run complete: {stats}")
    except Exception as e:
        logger.error(f"Scheduled pipeline run failed: {e}")


async def scheduled_hash_cleanup():
    """Wrapper for scheduled hash cleanup."""
    try:
        deleted = await cleanup_old_hashes(max_age_hours=24)
        if deleted > 0:
            logger.info(f"Hash cleanup: removed {deleted} old hashes")
    except Exception as e:
        logger.error(f"Hash cleanup failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    # Startup
    logger.info("Starting Crypto News Pipeline...")
    logger.info(f"Poll interval: {settings.poll_interval_min} min")
    logger.info(f"Impact threshold: {settings.impact_threshold}")
    logger.info(f"Watched tickers: {settings.tickers_list}")

    # Schedule pipeline
    scheduler.add_job(
        scheduled_pipeline_run,
        trigger=IntervalTrigger(minutes=settings.poll_interval_min),
        id="pipeline_run",
        name="RSS Pipeline",
        replace_existing=True,
    )

    # Schedule hash cleanup every 6 hours
    scheduler.add_job(
        scheduled_hash_cleanup,
        trigger=IntervalTrigger(hours=6),
        id="hash_cleanup",
        name="Hash Cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started")

    yield

    # Shutdown
    logger.info("Shutting down...")
    scheduler.shutdown(wait=False)
    await close_http_client()
    await close_bot()
    await engine.dispose()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Crypto News Pipeline",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health check for Railway."""
    return {"status": "ok"}


@app.get("/status")
async def status():
    """Pipeline status: last run stats + article counts."""
    try:
        async with async_session() as session:
            # Last pipeline run
            last_run = await session.execute(
                sa.select(PipelineLog)
                .order_by(PipelineLog.run_at.desc())
                .limit(1)
            )
            run = last_run.scalar_one_or_none()

            # Article counts
            total = await session.execute(
                sa.select(sa.func.count()).select_from(Article)
            )
            posted = await session.execute(
                sa.select(sa.func.count())
                .select_from(Article)
                .where(Article.status == "posted")
            )

            return {
                "status": "ok",
                "last_run": {
                    "run_at": run.run_at.isoformat() if run else None,
                    "fetched": run.fetched if run else 0,
                    "dupes": run.dupes if run else 0,
                    "scored": run.scored if run else 0,
                    "posted": run.posted if run else 0,
                    "duration_ms": run.duration_ms if run else 0,
                    "errors": run.errors if run else [],
                },
                "articles": {
                    "total": total.scalar_one(),
                    "posted": posted.scalar_one(),
                },
                "config": {
                    "poll_interval_min": settings.poll_interval_min,
                    "impact_threshold": settings.impact_threshold,
                    "tickers": settings.tickers_list,
                    "feeds": len(settings.rss_feeds),
                },
            }
    except Exception as e:
        logger.error(f"Status endpoint error: {e}")
        return {"status": "error", "message": str(e)}


@app.post("/run")
async def trigger_run():
    """Manually trigger a pipeline run. For admin/debugging."""
    try:
        stats = await run_pipeline()
        return {"status": "ok", "stats": stats}
    except Exception as e:
        logger.error(f"Manual run failed: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
