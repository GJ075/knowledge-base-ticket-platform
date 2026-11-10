"""add document soft delete

Revision ID: 0002_soft_delete
Revises: 0001_initial
Create Date: 2026-11-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_soft_delete"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "is_deleted")
