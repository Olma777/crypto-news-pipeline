"""Telegram channel poster. Sends formatted messages via aiogram."""

import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from app.config import settings
from app.formatter import format_message
from app.models import ArticleCandidate, ScoringResult

logger = logging.getLogger(__name__)

# Shared bot instance
_bot: Bot | None = None

# Rate limit: minimum seconds between posts
POST_DELAY_SECONDS = 3


def get_bot() -> Bot:
    """Get or create shared Bot instance."""
    global _bot
    if _bot is None:
        _bot = Bot(token=settings.telegram_bot_token)
    return _bot


async def send_to_channel(
    article: ArticleCandidate,
    score: ScoringResult,
) -> int | None:
    """
    Format and send a single article to Telegram channel.
    Returns tg_message_id on success, None on failure.
    """
    bot = get_bot()
    message_text = format_message(article, score)
    channel_id = settings.telegram_channel_id

    try:
        msg = await bot.send_message(
            chat_id=channel_id,
            text=message_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=False,
        )
        logger.info(
            f"Posted to channel: [{article.source}] '{article.title[:50]}' "
            f"(msg_id={msg.message_id})"
        )
        return msg.message_id

    except Exception as e:
        logger.error(f"Failed to post '{article.title[:50]}': {e}")
        return None


async def post_articles(
    scored_articles: list[tuple[ArticleCandidate, ScoringResult]],
) -> list[tuple[ArticleCandidate, ScoringResult, int]]:
    """
    Post a batch of scored articles to Telegram channel.
    Respects rate limit (3s delay between posts).
    Returns list of (article, score, tg_message_id) for successfully posted.
    """
    if not scored_articles:
        return []

    posted: list[tuple[ArticleCandidate, ScoringResult, int]] = []

    for i, (article, score) in enumerate(scored_articles):
        # Rate limit delay (skip before first message)
        if i > 0:
            await asyncio.sleep(POST_DELAY_SECONDS)

        msg_id = await send_to_channel(article, score)
        if msg_id is not None:
            posted.append((article, score, msg_id))

    logger.info(f"Posted {len(posted)}/{len(scored_articles)} articles to channel")
    return posted


async def close_bot() -> None:
    """Close bot session. Call on shutdown."""
    global _bot
    if _bot is not None:
        await _bot.session.close()
        _bot = None
