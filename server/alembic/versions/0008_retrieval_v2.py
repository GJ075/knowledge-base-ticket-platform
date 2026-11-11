"""retrieval v2: chunk metadata, full-text index, eval retrieval config

Revision ID: 0008_retrieval_v2
Revises: 0007_document_trash
Create Date: 2026-11-11

部署说明：本迁移只新增 content_tsv 列，不回填历史分块。
执行 upgrade 之后必须运行 `python -m scripts.backfill_tsv`
（或 `python -m scripts.reindex_all`），否则混合检索的稀疏路
对所有旧分块静默返回空结果。/health/ready 的 fts 组件会暴露该状态。
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_retrieval_v2"
down_revision: Union[str, None] = "0007_document_trash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("doc_type", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("department", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("version", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("effective_date", sa.Date(), nullable=True))
    op.add_column(
        "documents",
        sa.Column(
            "source",
            sa.String(16),
            server_default="internal",
            nullable=False,
        ),
    )

    op.add_column(
        "document_chunks",
        sa.Column(
            "heading_path",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column(
            "unit_type",
            sa.String(16),
            server_default="paragraph",
            nullable=False,
        ),
    )
    op.add_column(
        "document_chunks",
        sa.Column("char_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "document_chunks",
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "document_chunks",
        sa.Column("content_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "document_chunks",
        sa.Column("content_tsv", postgresql.TSVECTOR(), nullable=True),
    )

    op.create_index(
        "ix_chunks_content_tsv",
        "document_chunks",
        ["content_tsv"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_chunks_content_hash",
        "document_chunks",
        ["content_hash"],
    )

    op.add_column(
        "eval_runs",
        sa.Column("retrieval_config", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("eval_runs", "retrieval_config")

    op.drop_index("ix_chunks_content_hash", table_name="document_chunks")
    op.drop_index("ix_chunks_content_tsv", table_name="document_chunks")

    op.drop_column("document_chunks", "content_tsv")
    op.drop_column("document_chunks", "content_hash")
    op.drop_column("document_chunks", "token_count")
    op.drop_column("document_chunks", "char_count")
    op.drop_column("document_chunks", "unit_type")
    op.drop_column("document_chunks", "heading_path")

    op.drop_column("documents", "source")
    op.drop_column("documents", "effective_date")
    op.drop_column("documents", "version")
    op.drop_column("documents", "department")
    op.drop_column("documents", "doc_type")
