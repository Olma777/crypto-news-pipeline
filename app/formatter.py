"""Telegram message formatter. Builds HTML posts from scored articles."""

from urllib.parse import urlparse

from app.models import ArticleCandidate, ScoringResult


def format_tickers(tickers: list[str]) -> str:
    """Format ticker list as hashtag string."""
    if not tickers:
        return ""
    return " ".join(f"#{t}" for t in tickers)


def get_source_domain(url: str) -> str:
    """Extract clean domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return "source"


def escape_html(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_message(article: ArticleCandidate, score: ScoringResult) -> str:
    """
    Build formatted Telegram HTML message.

    Format:
    {title_ru}

    {body_ru}

    #BTC #ETH

    ➖➖➖➖➖➖➖➖
    🔗 source_domain
    """
    title_ru = escape_html(score.title_ru)
    body_ru = escape_html(score.body_ru)
    tickers = format_tickers(score.tickers)
    domain = get_source_domain(article.source_url)
    source_link = article.source_url

    parts = []

    # Title (bold)
    parts.append(f"<b>{title_ru}</b>")

    # Body
    parts.append(f"\n{body_ru}")

    # Tickers
    if tickers:
        parts.append(f"\n{tickers}")

    # Separator + source
    parts.append("\n\u2796\u2796\u2796\u2796\u2796\u2796\u2796\u2796")
    parts.append(f'\U0001f517 <a href="{source_link}">{escape_html(domain)}</a>')

    return "\n".join(parts)
