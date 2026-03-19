"""Telegram message formatter. Builds HTML posts from scored articles."""

from urllib.parse import urlparse

from app.models import ArticleCandidate, ScoringResult


def get_impact_marker(score: int) -> str:
    """Return emoji marker based on impact score."""
    if score >= 8:
        return "\U0001f534"  # red circle
    elif score >= 6:
        return "\U0001f7e1"  # yellow circle
    return ""


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

    Template:
    [emoji] HIGH IMPACT / NOTABLE

    Title in Russian

    Body in Russian

    #BTC #ETH

    [link emoji] source_domain
    """
    marker = get_impact_marker(score.impact_score)
    impact_label = "HIGH IMPACT" if score.impact_score >= 8 else "NOTABLE"

    title_ru = escape_html(score.title_ru)
    body_ru = escape_html(score.body_ru)
    tickers = format_tickers(score.tickers)
    domain = get_source_domain(article.source_url)
    source_link = article.source_url

    parts = []

    # Header line
    parts.append(f"{marker} <b>{impact_label}</b>")

    # Title
    parts.append(f"\n<b>{title_ru}</b>")

    # Body
    parts.append(f"\n{body_ru}")

    # Tickers
    if tickers:
        parts.append(f"\n{tickers}")

    # Source link
    parts.append(f'\n\U0001f517 <a href="{source_link}">{escape_html(domain)}</a>')

    return "\n".join(parts)
