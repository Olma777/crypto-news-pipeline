"""initial

Revision ID: 001
Revises:
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from sqlalchemy import inspect

    bind = op.get_bind()
    inspector = inspect(bind)
    existing = inspector.get_table_names()

    if "articles" not in existing:
        op.create_table(
            "articles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source", sa.String(64), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False, unique=True),
            sa.Column("title_en", sa.Text(), nullable=False),
            sa.Column("summary_en", sa.Text()),
            sa.Column("title_ru", sa.Text()),
            sa.Column("body_ru", sa.Text()),
            sa.Column("tickers", ARRAY(sa.String(16)), server_default="{}"),
            sa.Column("impact_score", sa.SmallInteger()),
            sa.Column("impact_reason", sa.Text()),
            sa.Column("content_hash", sa.String(64), nullable=False),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("posted_at", sa.DateTime(timezone=True)),
            sa.Column("tg_message_id", sa.BigInteger()),
            sa.Column("status", sa.String(16), server_default="new"),
            sa.CheckConstraint("impact_score BETWEEN 1 AND 10", name="ck_impact_score_range"),
            sa.CheckConstraint(
                "status IN ('new','scored','posted','skipped','error')",
                name="ck_status_values",
            ),
        )

    if "content_hashes" not in existing:
        op.create_table(
            "content_hashes",
            sa.Column("hash", sa.String(64), primary_key=True),
            sa.Column("article_id", sa.Integer(), sa.ForeignKey("articles.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        )

    if "pipeline_log" not in existing:
        op.create_table(
            "pipeline_log",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("run_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.Column("source", sa.String(64)),
            sa.Column("fetched", sa.Integer(), server_default="0"),
            sa.Column("dupes", sa.Integer(), server_default="0"),
            sa.Column("scored", sa.Integer(), server_default="0"),
            sa.Column("posted", sa.Integer(), server_default="0"),
            sa.Column("errors", ARRAY(sa.Text())),
            sa.Column("duration_ms", sa.Integer()),
        )


def downgrade() -> None:
    op.drop_table("pipeline_log")
    op.drop_table("content_hashes")
    op.drop_table("articles")
