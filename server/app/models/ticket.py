import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import User


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "type IN ('it_fault', 'permission_request', 'data_request', 'other')",
            name="ck_tickets_type",
        ),
        CheckConstraint(
            "priority IN ('low', 'medium', 'high', 'urgent')",
            name="ck_tickets_priority",
        ),
        CheckConstraint(
            "status IN ('new', 'pending_assignment', 'in_progress', 'completed', "
            "'pending_user_confirmation', 'returned', 'modified', 'resolved')",
            name="ck_tickets_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_no: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    expected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    is_backfilled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    attachments: Mapped[list["TicketAttachment"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan"
    )
    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketEvent.created_at",
    )
    creator: Mapped[User] = relationship(
        foreign_keys=[created_by], lazy="selectin"
    )
    assignee: Mapped[User | None] = relationship(
        foreign_keys=[assignee_id], lazy="selectin"
    )


class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    object_key: Mapped[str] = mapped_column(
        String(512), unique=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="attachments")
    uploader: Mapped[User] = relationship(
        foreign_keys=[uploaded_by], lazy="selectin"
    )


class TicketEvent(Base):
    __tablename__ = "ticket_events"
    __table_args__ = (
        CheckConstraint(
            "action IN ('created', 'backfilled', 'approved', 'rejected', "
            "'assigned', 'marked_completed', 'confirmed_resolved', "
            "'confirmed_unresolved', 'marked_modified', 'edited')",
            name="ck_ticket_events_action",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped[Ticket] = relationship(back_populates="events")
    actor: Mapped[User] = relationship(
        foreign_keys=[actor_id], lazy="selectin"
    )
