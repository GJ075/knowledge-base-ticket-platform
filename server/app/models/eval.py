import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class EvalDataset(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
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

    cases: Mapped[list["EvalCase"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="EvalCase.sort_order",
        lazy="selectin",
    )


class EvalCase(Base):
    __tablename__ = "eval_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    tags: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    sort_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
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

    dataset: Mapped[EvalDataset] = relationship(back_populates="cases")
    turns: Mapped[list["EvalTurn"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="EvalTurn.turn_index",
        lazy="selectin",
    )


class EvalTurn(Base):
    __tablename__ = "eval_turns"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "turn_index", name="uq_eval_turns_case_index"
        ),
        CheckConstraint(
            "expected_type IN ('answerable', 'unanswerable')",
            name="ck_eval_turns_expected_type",
        ),
        CheckConstraint(
            "turn_index BETWEEN 1 AND 5", name="ck_eval_turns_index"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="answerable"
    )
    required_document_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
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

    case: Mapped[EvalCase] = relationship(back_populates="turns")


class EvalRun(Base):
    __tablename__ = "eval_runs"
    __table_args__ = (
        CheckConstraint(
            "retrieval_mode IN ('question', 'rewritten')",
            name="ck_eval_runs_retrieval_mode",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_eval_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    retrieval_mode: Mapped[str] = mapped_column(
        String(24), nullable=False, default="question"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )
    baseline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    total_items: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    completed_items: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retrieval_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvalRunItem(Base):
    __tablename__ = "eval_run_items"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "case_id", "turn_index", name="uq_eval_run_items_turn"
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'passed', 'failed', "
            "'invalid', 'error', 'cancelled')",
            name="ck_eval_run_items_status",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    case_title: Mapped[str] = mapped_column(String(255), nullable=False)
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_type: Mapped[str] = mapped_column(String(16), nullable=False)
    required_document_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    retrieval_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieved: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    judge_passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    refused: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    judge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    retrieval_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    retrieval_recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    retrieval_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    citation_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    citation_precision: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    used_citation_hit: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    used_citation_precision: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    invalid_refs: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    citation_fallback: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    rerank_degraded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    invalid_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
