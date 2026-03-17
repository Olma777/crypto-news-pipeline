"""Async SQLAlchemy engine, session factory, and ORM models."""

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=5,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    source_url: Mapped[str] = mapped_column(sa.Text, nullable=False, unique=True)
    title_en: Mapped[str] = mapped_column(sa.Text, nullable=False)
    summary_en: Mapped[str | None] = mapped_column(sa.Text)
    title_ru: Mapped[str | None] = mapped_column(sa.Text)
    body_ru: Mapped[str | None] = mapped_column(sa.Text)
    tickers: Mapped[list[str] | None] = mapped_column(ARRAY(sa.String(16)), server_default="{}")
    impact_score: Mapped[int | None] = mapped_column(sa.SmallInteger)
    impact_reason: Mapped[str | None] = mapped_column(sa.Text)
    content_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    published_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    posted_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    tg_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    status: Mapped[str] = mapped_column(
        sa.String(16),
        server_default="new",
    )

    __table_args__ = (
        sa.CheckConstraint("impact_score BETWEEN 1 AND 10", name="ck_impact_score_range"),
        sa.CheckConstraint(
            "status IN ('new','scored','posted','skipped','error')",
            name="ck_status_values",
        ),
    )


class ContentHash(Base):
    __tablename__ = "content_hashes"

    hash: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    article_id: Mapped[int | None] = mapped_column(sa.ForeignKey("articles.id"))
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )


class PipelineLog(Base):
    __tablename__ = "pipeline_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.func.now()
    )
    source: Mapped[str | None] = mapped_column(sa.String(64))
    fetched: Mapped[int] = mapped_column(default=0)
    dupes: Mapped[int] = mapped_column(default=0)
    scored: Mapped[int] = mapped_column(default=0)
    posted: Mapped[int] = mapped_column(default=0)
    errors: Mapped[list[str] | None] = mapped_column(ARRAY(sa.Text))
    duration_ms: Mapped[int | None] = mapped_column(sa.Integer)
