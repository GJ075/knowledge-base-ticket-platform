import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "index_status IN ('pending', 'indexing', 'ready', 'failed')",
            name="ck_documents_index_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    object_key: Mapped[str] = mapped_column(
        String(512), unique=True, nullable=False
    )
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    index_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    is_deleted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    uploader: Mapped[User] = relationship(
        foreign_keys=[uploaded_by], lazy="selectin"
    )


class DocumentChange(Base):
    __tablename__ = "document_changes"
    __table_args__ = (
        CheckConstraint(
            "action IN ('create', 'update', 'delete')",
            name="ck_document_changes_action",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_document_changes_status",
        ),
        CheckConstraint(
            "(action = 'create' AND document_id IS NULL AND title IS NOT NULL "
            "AND object_key IS NOT NULL) OR "
            "(action = 'update' AND document_id IS NOT NULL AND "
            "(title IS NOT NULL OR object_key IS NOT NULL)) OR "
            "(action = 'delete' AND document_id IS NOT NULL AND object_key IS NULL)",
            name="ck_document_changes_shape",
        ),
        CheckConstraint(
            "(status = 'pending' AND reviewed_by IS NULL AND reviewed_at IS NULL) OR "
            "(status IN ('approved', 'rejected') AND reviewed_by IS NOT NULL "
            "AND reviewed_at IS NOT NULL)",
            name="ck_document_changes_review",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    document: Mapped[Document | None] = relationship(
        foreign_keys=[document_id], lazy="selectin"
    )
    requester: Mapped[User] = relationship(
        foreign_keys=[requested_by], lazy="selectin"
    )
    reviewer: Mapped[User | None] = relationship(
        foreign_keys=[reviewed_by], lazy="selectin"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_doc_index"
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")
