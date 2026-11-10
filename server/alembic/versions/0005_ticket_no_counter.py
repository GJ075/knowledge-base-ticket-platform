"""add transactional ticket number counter

Revision ID: 0005_ticket_no_counter
Revises: 0004_backfilled_event
Create Date: 2026-11-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_ticket_no_counter"
down_revision: Union[str, None] = "0004_backfilled_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_no_counters",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column(
            "last_value",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.execute(
        """
        INSERT INTO ticket_no_counters (day, last_value)
        SELECT to_date(substring(ticket_no from 2 for 8), 'YYYYMMDD'),
               MAX(substring(ticket_no from 11)::integer)
        FROM tickets
        WHERE ticket_no ~ '^T[0-9]{8}-[0-9]{6}$'
        GROUP BY 1
        ON CONFLICT (day) DO UPDATE SET
            last_value = GREATEST(
                ticket_no_counters.last_value,
                EXCLUDED.last_value
            )
        """
    )


def downgrade() -> None:
    op.drop_table("ticket_no_counters")
