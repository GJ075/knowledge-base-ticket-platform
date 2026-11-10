"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-09
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SEQUENCE IF NOT EXISTS ticket_no_seq START 1")

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('employee', 'leader')",
            name="ck_users_role",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "index_status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "index_status IN ('pending','indexing','ready','failed')",
            name="ck_documents_index_status",
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )

    op.create_table(
        "document_changes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=128), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "reviewed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "action IN ('create','update','delete')",
            name="ck_document_changes_action",
        ),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="ck_document_changes_status",
        ),
        sa.CheckConstraint(
            "(action = 'create' AND document_id IS NULL AND title IS NOT NULL "
            "AND object_key IS NOT NULL) OR "
            "(action = 'update' AND document_id IS NOT NULL AND "
            "(title IS NOT NULL OR object_key IS NOT NULL)) OR "
            "(action = 'delete' AND document_id IS NOT NULL AND object_key IS NULL)",
            name="ck_document_changes_shape",
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND reviewed_by IS NULL AND reviewed_at IS NULL) OR "
            "(status IN ('approved','rejected') AND reviewed_by IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_document_changes_review",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_document_changes_status_created",
        "document_changes",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_document_changes_requested_by",
        "document_changes",
        ["requested_by"],
    )
    op.create_index(
        "ix_document_changes_document_id",
        "document_changes",
        ["document_id"],
    )

    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_document_chunks_doc_index",
        ),
    )
    op.create_index(
        "ix_document_chunks_document_id",
        "document_chunks",
        ["document_id"],
    )
    op.execute(
        "CREATE INDEX idx_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )

    op.create_table(
        "conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "title",
            sa.String(length=255),
            server_default="新对话",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_user_updated",
        "conversations",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "citations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "role IN ('user','assistant')",
            name="ck_messages_role",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_messages_conversation_created",
        "messages",
        ["conversation_id", "created_at"],
    )

    op.create_table(
        "tickets",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("ticket_no", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column(
            "expected_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "assignee_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column(
            "version",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "type IN ('it_fault','permission_request','data_request','other')",
            name="ck_tickets_type",
        ),
        sa.CheckConstraint(
            "priority IN ('low','medium','high','urgent')",
            name="ck_tickets_priority",
        ),
        sa.CheckConstraint(
            "status IN ('new','pending_assignment','in_progress','completed',"
            "'pending_user_confirmation','returned','modified','resolved')",
            name="ck_tickets_status",
        ),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticket_no"),
    )
    op.create_index(
        "ix_tickets_status_created",
        "tickets",
        ["status", "created_at"],
    )
    op.create_index("ix_tickets_created_by", "tickets", ["created_by"])
    op.create_index(
        "ix_tickets_assignee_status",
        "tickets",
        ["assignee_id", "status"],
    )

    op.create_table(
        "ticket_attachments",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "uploaded_by",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        "ix_ticket_attachments_ticket_id",
        "ticket_attachments",
        ["ticket_id"],
    )

    op.create_table(
        "ticket_events",
        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "ticket_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=True),
        sa.Column("to_status", sa.String(length=32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('created','approved','rejected','assigned',"
            "'marked_completed','confirmed_resolved','confirmed_unresolved',"
            "'marked_modified','edited')",
            name="ck_ticket_events_action",
        ),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ticket_events_ticket_created",
        "ticket_events",
        ["ticket_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("ticket_events")
    op.drop_table("ticket_attachments")
    op.drop_table("tickets")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("document_chunks")
    op.drop_table("document_changes")
    op.drop_table("documents")
    op.drop_table("users")
    op.execute("DROP SEQUENCE IF EXISTS ticket_no_seq")
