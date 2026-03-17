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

    @property
    def tickers_list(self) -> list[str]:
        return [t.strip().upper() for t in self.watched_tickers.split(",") if t.strip()]

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
