"""Claude Sonnet 4.6 scorer. Impact scoring + Russian translation."""

import asyncio
import json
import logging

import anthropic
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import Article, async_session
from app.models import ArticleCandidate, ScoringResult

logger = logging.getLogger(__name__)

# Anthropic client — created once
_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    """Get or create Anthropic async client."""
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


SYSTEM_PROMPT = """You are a crypto news analyst for a Russian-language Telegram channel.
Your job: score news by market impact and translate to Russian.

IMPACT SCORING (1-10):
8-10: Regulatory decisions (SEC, EU, CFTC), ETF approvals/rejections,
      major hacks (>$10M), Fed rate decisions, CPI data,
      institutional buys (Strategy, sovereign funds), major exchange
      listings/delistings, protocol-breaking vulnerabilities
7:    Large partnerships, mainnet launches, significant upgrades
      (hard forks), whale movements (>$100M)
5-6:  Mid-tier partnerships, testnet launches, moderate whale moves,
      on-chain anomalies, governance votes
1-4:  Analyst opinions, price predictions, sentiment commentary,
      minor project updates, rehashed news

TRANSLATION RULES:
- Translate title and write 2-3 sentence summary in Russian
- Keep crypto terms in English: staking, DeFi, L2, DEX, CEX, TVL, APY
- Keep project names in English: Chainlink, Avalanche, Binance
- DO NOT add facts not present in the source text
- DO NOT add your opinion or analysis

CRITICAL — HUMAN WRITING STYLE FOR RUSSIAN TEXT:
Write like a live news editor, NOT like AI. Your Russian text MUST avoid these patterns:
- Inflated significance: never use "является свидетельством", "знаменует собой",
  "поворотный момент", "подчёркивает важность", "эволюция", "ландшафт"
- Promotional language: never use "впечатляющий", "прорывной", "выдающийся",
  "захватывающий", "уникальный", "всемирно известный"
- AI vocabulary: never use "кроме того", "ключевой" (as filler), "содействовать",
  "ландшафт", "важнейший", "демонстрировать", "сложное взаимодействие"
- Vague references: never use "по мнению экспертов", "наблюдатели отмечают"
  (unless quoting a specific named source)
- Challenge-and-prospect template: never use "несмотря на вызовы, продолжает развиваться"
- Cliché conclusions: never use "будущее выглядит многообещающим"
- Filler words: never use "для того чтобы", "важно отметить", "на данный момент времени"
- Negative parallelisms: avoid "не только...но и", "это не просто"

Instead: short sentences, concrete facts, no fluff. Write as if for a news wire service.
Example good style: "SEC одобрила спотовый ETH ETF. Торги начнутся 23 июля на CBOE и NYSE."
Example bad style: "Это знаменует собой ключевой поворотный момент в эволюции криптоландшафта."

DEDUP CHECK:
Compare against these recent headlines: {recent_headlines}
If this is substantially the same story as any of them, set is_duplicate: true

RESPOND ONLY IN JSON (no markdown, no backticks):
{
  "impact_score": 8,
  "impact_reason": "brief reason in English",
  "tickers": ["BTC"],
  "title_ru": "Russian title — short, factual, no AI fluff",
  "body_ru": "2-3 sentence summary in Russian — news wire style",
  "is_duplicate": false
}"""


async def get_recent_headlines(limit: int = 20) -> list[str]:
    """Fetch last N posted article headlines from DB for dedup context."""
    try:
        async with async_session() as session:
            result = await session.execute(
                sa.select(Article.title_en)
                .where(Article.status == "posted")
                .order_by(Article.posted_at.desc())
                .limit(limit)
            )
            return [row[0] for row in result.fetchall()]
    except Exception as e:
        logger.warning(f"Failed to fetch recent headlines: {e}")
        return []


def build_user_message(article: ArticleCandidate) -> str:
    """Build user message with article content for scoring."""
    parts = [f"Title: {article.title}"]
    if article.summary:
        parts.append(f"Summary: {article.summary}")
    parts.append(f"Source: {article.source}")
    return "\n".join(parts)


def parse_scoring_response(raw_text: str) -> ScoringResult | None:
    """Parse Claude's JSON response into ScoringResult. Returns None on failure."""
    # Strip potential markdown fencing
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        data = json.loads(text)
        return ScoringResult(
            impact_score=data.get("impact_score", 1),
            impact_reason=data.get("impact_reason", ""),
            tickers=data.get("tickers", []),
            title_ru=data.get("title_ru", ""),
            body_ru=data.get("body_ru", ""),
            is_duplicate=data.get("is_duplicate", False),
        )
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.error(f"Failed to parse scoring response: {e}\nRaw: {text[:500]}")
        return None


async def score_article(
    article: ArticleCandidate,
    recent_headlines: list[str],
) -> ScoringResult | None:
    """
    Score a single article using Claude Sonnet 4.6.
    Returns ScoringResult or None on failure.
    Retries once on API error.
    """
    client = get_client()
    headlines_str = "\n".join(f"- {h}" for h in recent_headlines) if recent_headlines else "(none yet)"
    system = SYSTEM_PROMPT.replace("{recent_headlines}", headlines_str)
    user_msg = build_user_message(article)

    for attempt in range(2):  # max 2 attempts
        try:
            response = await client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1024,
                system=system,
                messages=[{"role": "user", "content": user_msg}],
            )

            raw_text = ""
            for block in response.content:
                if block.type == "text":
                    raw_text += block.text

            result = parse_scoring_response(raw_text)
            if result is not None:
                logger.info(
                    f"Scored [{article.source}] '{article.title[:60]}' -> "
                    f"impact={result.impact_score}, dup={result.is_duplicate}"
                )
                return result
            else:
                logger.warning(f"Parse failed for '{article.title[:60]}', attempt {attempt + 1}")
                if attempt == 0:
                    continue
                return None

        except anthropic.RateLimitError:
            if attempt == 0:
                logger.warning("Rate limited by Anthropic, waiting 10s...")
                await asyncio.sleep(10)
                continue
            logger.error("Rate limited twice, skipping article")
            return None

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error (attempt {attempt + 1}): {e}")
            if attempt == 0:
                await asyncio.sleep(2)
                continue
            return None

        except Exception as e:
            logger.error(f"Unexpected error scoring article: {e}")
            return None

    return None


async def score_articles(
    candidates: list[ArticleCandidate],
) -> list[tuple[ArticleCandidate, ScoringResult]]:
    """
    Score a batch of articles. Fetches recent headlines once,
    then scores each article sequentially (to respect rate limits).
    Returns list of (article, score) tuples that passed threshold.
    Skips duplicates and low-impact articles.
    """
    if not candidates:
        return []

    recent_headlines = await get_recent_headlines()
    results: list[tuple[ArticleCandidate, ScoringResult]] = []
    skipped_low = 0
    skipped_dup = 0
    errors = 0

    for article in candidates:
        result = await score_article(article, recent_headlines)

        if result is None:
            errors += 1
            continue

        if result.is_duplicate:
            skipped_dup += 1
            logger.info(f"Skipped duplicate: '{article.title[:60]}'")
            continue

        if result.impact_score < settings.impact_threshold:
            skipped_low += 1
            continue

        results.append((article, result))
        # Add to headlines for subsequent dedup context
        recent_headlines.insert(0, article.title)
        if len(recent_headlines) > 20:
            recent_headlines.pop()

    logger.info(
        f"Scoring done: {len(candidates)} articles -> {len(results)} passed "
        f"(low={skipped_low}, dup={skipped_dup}, err={errors})"
    )

    return results
