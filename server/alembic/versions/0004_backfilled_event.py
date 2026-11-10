"""allow backfilled ticket event action

Revision ID: 0004_backfilled_event
Revises: 0003_ticket_backfill
Create Date: 2026-11-10
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_backfilled_event"
down_revision: Union[str, None] = "0003_ticket_backfill"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIONS = (
    "'created','backfilled','approved','rejected','assigned',"
    "'marked_completed','confirmed_resolved','confirmed_unresolved',"
    "'marked_modified','edited'"
)
_OLD_ACTIONS = (
    "'created','approved','rejected','assigned',"
    "'marked_completed','confirmed_resolved','confirmed_unresolved',"
    "'marked_modified','edited'"
)


def upgrade() -> None:
    op.drop_constraint(
        "ck_ticket_events_action", "ticket_events", type_="check"
    )
    op.create_check_constraint(
        "ck_ticket_events_action",
        "ticket_events",
        f"action IN ({_ACTIONS})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_ticket_events_action", "ticket_events", type_="check"
    )
    op.create_check_constraint(
        "ck_ticket_events_action",
        "ticket_events",
        f"action IN ({_OLD_ACTIONS})",
    )
