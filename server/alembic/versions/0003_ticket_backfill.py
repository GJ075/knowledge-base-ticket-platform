"""add ticket backfill flag

Revision ID: 0003_ticket_backfill
Revises: 0002_soft_delete
Create Date: 2026-11-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_ticket_backfill"
down_revision: Union[str, None] = "0002_soft_delete"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "is_backfilled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("tickets", "is_backfilled")
