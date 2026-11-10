"""add evaluation system

Revision ID: 0006_evaluation
Revises: 0005_ticket_no_counter
Create Date: 2026-11-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_evaluation"
down_revision: Union[str, None] = "0005_ticket_no_counter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "can_evaluate",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )

    op.create_table(
        "eval_datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )

    op.create_table(
        "eval_cases",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column(
            "tags", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            "sort_order", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )
    op.create_index(
        "ix_eval_cases_dataset_id", "eval_cases", ["dataset_id"]
    )

    op.create_table(
        "eval_turns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column(
            "expected_type", sa.String(16), nullable=False,
            server_default="answerable",
        ),
        sa.Column(
            "required_document_ids", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "case_id", "turn_index", name="uq_eval_turns_case_index"
        ),
        sa.CheckConstraint(
            "expected_type IN ('answerable', 'unanswerable')",
            name="ck_eval_turns_expected_type",
        ),
        sa.CheckConstraint(
            "turn_index BETWEEN 1 AND 5", name="ck_eval_turns_index"
        ),
    )
    op.create_index("ix_eval_turns_case_id", "eval_turns", ["case_id"])

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "dataset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_datasets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "retrieval_mode", sa.String(24), nullable=False,
            server_default="question",
        ),
        sa.Column(
            "status", sa.String(16), nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "baseline_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "total_items", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column(
            "completed_items", sa.Integer(),
            server_default=sa.text("0"), nullable=False,
        ),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "cancel_requested", sa.Boolean(),
            server_default=sa.text("false"), nullable=False,
        ),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "finished_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.CheckConstraint(
            "retrieval_mode IN ('question', 'rewritten')",
            name="ck_eval_runs_retrieval_mode",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', "
            "'cancelled')",
            name="ck_eval_runs_status",
        ),
    )
    op.create_index("ix_eval_runs_dataset_id", "eval_runs", ["dataset_id"])
    op.create_index("ix_eval_runs_status", "eval_runs", ["status"])

    op.create_table(
        "eval_run_items",
        sa.Column(
            "id", sa.BigInteger(), primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("eval_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("case_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("case_title", sa.String(255), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column("expected_type", sa.String(16), nullable=False),
        sa.Column(
            "required_document_ids", postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"), nullable=False,
        ),
        sa.Column(
            "status", sa.String(16), nullable=False,
            server_default="pending",
        ),
        sa.Column("retrieval_query", sa.Text(), nullable=True),
        sa.Column("retrieved", postgresql.JSONB(), nullable=True),
        sa.Column("citations", postgresql.JSONB(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("judge_score", sa.Integer(), nullable=True),
        sa.Column("judge_passed", sa.Boolean(), nullable=True),
        sa.Column("refused", sa.Boolean(), nullable=True),
        sa.Column("judge_reason", sa.Text(), nullable=True),
        sa.Column("retrieval_hit", sa.Boolean(), nullable=True),
        sa.Column("retrieval_recall", sa.Float(), nullable=True),
        sa.Column("retrieval_rank", sa.Integer(), nullable=True),
        sa.Column("citation_hit", sa.Boolean(), nullable=True),
        sa.Column("citation_precision", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("invalid_reason", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint(
            "run_id", "case_id", "turn_index", name="uq_eval_run_items_turn"
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'passed', 'failed', "
            "'invalid', 'error', 'cancelled')",
            name="ck_eval_run_items_status",
        ),
    )
    op.create_index(
        "ix_eval_run_items_run_id", "eval_run_items", ["run_id"]
    )
    op.create_index(
        "ix_eval_run_items_run_status",
        "eval_run_items",
        ["run_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_eval_run_items_run_status", "eval_run_items")
    op.drop_index("ix_eval_run_items_run_id", "eval_run_items")
    op.drop_table("eval_run_items")
    op.drop_index("ix_eval_runs_status", "eval_runs")
    op.drop_index("ix_eval_runs_dataset_id", "eval_runs")
    op.drop_table("eval_runs")
    op.drop_index("ix_eval_turns_case_id", "eval_turns")
    op.drop_table("eval_turns")
    op.drop_index("ix_eval_cases_dataset_id", "eval_cases")
    op.drop_table("eval_cases")
    op.drop_table("eval_datasets")
    op.drop_column("users", "can_evaluate")
