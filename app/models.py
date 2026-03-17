"""Pydantic models for pipeline data flow."""

from datetime import datetime

from pydantic import BaseModel, Field


class FeedSource(BaseModel):
    name: str
    url: str
    tier: int = 1


class ArticleCandidate(BaseModel):
    """Raw article from RSS feed before scoring."""

    source: str
    source_url: str
    title: str
    summary: str = ""
    published_at: datetime
    content_hash: str = ""


class ScoringResult(BaseModel):
    """Response from Claude Sonnet scoring."""

    impact_score: int = Field(ge=1, le=10)
    impact_reason: str = ""
    tickers: list[str] = []
    title_ru: str = ""
    body_ru: str = ""
    is_duplicate: bool = False


class PipelineRunStats(BaseModel):
    """Stats for a single pipeline run."""

    source: str = "all"
    fetched: int = 0
    dupes: int = 0
    scored: int = 0
    posted: int = 0
    errors: list[str] = []
    duration_ms: int = 0
