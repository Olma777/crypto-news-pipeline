"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/news"

    # Anthropic
    anthropic_api_key: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""

    # Pipeline
    watched_tickers: str = "BTC,ETH,LINK,AVAX,XRP,BNB"
    impact_threshold: int = 6
    poll_interval_min: int = 15
    max_article_age_h: int = 6
    log_level: str = "INFO"

    # RSS Feeds configuration
    rss_feeds: list[dict] = [
        {"name": "CoinDesk", "url": "https://www.coindesk.com/arc/outboundfeeds/rss/", "tier": 1},
        {"name": "The Block", "url": "https://www.theblock.co/rss.xml", "tier": 1},
        {"name": "Decrypt", "url": "https://decrypt.co/feed", "tier": 1},
        {"name": "Cointelegraph", "url": "https://cointelegraph.com/rss", "tier": 2},
    ]

    @property
    def tickers_list(self) -> list[str]:
        return [t.strip().upper() for t in self.watched_tickers.split(",") if t.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Full names for ticker matching in article text
TICKER_NAMES: dict[str, list[str]] = {
    "BTC": ["bitcoin"],
    "ETH": ["ethereum"],
    "LINK": ["chainlink"],
    "AVAX": ["avalanche"],
    "XRP": ["ripple"],
    "BNB": ["binance"],
}
