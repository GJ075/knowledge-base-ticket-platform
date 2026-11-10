"""add document trash columns

Revision ID: 0007_document_trash
Revises: 0006_evaluation
Create Date: 2026-11-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_document_trash"
down_revision: Union[str, None] = "0006_evaluation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE documents
        SET deleted_at = updated_at,
            purged_at = updated_at
        WHERE is_deleted = true
        """
    )
    op.execute(
        """
        CREATE INDEX idx_documents_trash
        ON documents (deleted_at DESC)
        WHERE deleted_at IS NOT NULL AND purged_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_trash")
    op.drop_column("documents", "purged_at")
    op.drop_column("documents", "deleted_at")
