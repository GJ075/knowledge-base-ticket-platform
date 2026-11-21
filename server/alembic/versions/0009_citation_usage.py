"""citation usage tracking

Revision ID: 0009_citation_usage
Revises: 0008_retrieval_v2
Create Date: 2026-11-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_citation_usage"
down_revision: Union[str, None] = "0008_retrieval_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column(
            "citation_meta", postgresql.JSONB(), nullable=True
        ),
    )
    op.add_column(
        "eval_run_items",
        sa.Column("used_citation_hit", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "eval_run_items",
        sa.Column("used_citation_precision", sa.Float(), nullable=True),
    )
    op.add_column(
        "eval_run_items",
        sa.Column(
            "invalid_refs", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "eval_run_items",
        sa.Column(
            "citation_fallback",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )
    op.add_column(
        "eval_run_items",
        sa.Column(
            "rerank_degraded",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("eval_run_items", "rerank_degraded")
    op.drop_column("eval_run_items", "citation_fallback")
    op.drop_column("eval_run_items", "invalid_refs")
    op.drop_column("eval_run_items", "used_citation_precision")
    op.drop_column("eval_run_items", "used_citation_hit")
    op.drop_column("messages", "citation_meta")
