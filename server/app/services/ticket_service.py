import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import AppError
from app.models.ticket import Ticket, TicketAttachment, TicketEvent
from app.models.user import User
from app.schemas.ticket import (
    AssignRequest,
    AttachmentDownloadResponse,
    CompleteRequest,
    ConfirmRequest,
    ModifyCompleteRequest,
    RejectRequest,
    TicketAttachmentOut,
    TicketEventOut,
    TicketListResponse,
    TicketOut,
    TicketSummary,
    TicketUpdate,
)
from app.schemas.user import UserBrief
from app.services.mime_types import resolve_mime_type
from app.services.storage import (
    get_bytes_async,
    put_bytes_async,
    remove_object_async,
)

settings = get_settings()
BUCKET = settings.minio_ticket_bucket
logger = logging.getLogger("app")

TICKET_TYPES = {"it_fault", "permission_request", "data_request", "other"}
TICKET_PRIORITIES = {"low", "medium", "high", "urgent"}


def _user_brief(user: User) -> UserBrief:
    return UserBrief.model_validate(user)


async def _safe_rollback(db: AsyncSession) -> None:
    try:
        await db.rollback()
    except Exception as exc:
        logger.warning(
            "database rollback failed: %s: %s",
            type(exc).__name__,
            exc,
        )


def _attachment_out(
    attachment: TicketAttachment,
) -> TicketAttachmentOut:
    return TicketAttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        uploaded_by=_user_brief(attachment.uploader),
        created_at=attachment.created_at,
    )


def _event_out(event: TicketEvent) -> TicketEventOut:
    return TicketEventOut(
        id=event.id,
        actor=_user_brief(event.actor),
        action=event.action,
        from_status=event.from_status,
        to_status=event.to_status,
        comment=event.comment,
        created_at=event.created_at,
    )


def _available_actions(ticket: Ticket, user: User) -> list[str]:
    actions: list[str] = []
    handler_id = ticket.assignee_id or ticket.created_by

    if ticket.is_backfilled:
        if user.role == "leader" and ticket.status in (
            "new",
            "modified",
        ):
            actions.extend(["approve", "reject"])
        if user.id == handler_id and ticket.status == "returned":
            actions.extend(
                [
                    "edit",
                    "modify_complete",
                    "add_attachment",
                    "delete_attachment",
                ]
            )
        return actions

    if user.role == "leader":
        if ticket.status == "new":
            actions.extend(["approve", "reject"])
        elif ticket.status == "pending_assignment":
            actions.append("assign")
        elif ticket.status == "completed":
            actions.extend(["approve", "reject"])
        elif ticket.status == "modified":
            actions.extend(["approve", "reject"])
        elif (
            ticket.status == "pending_user_confirmation"
            and user.id == ticket.created_by
        ):
            actions.extend(["confirm_resolved", "confirm_unresolved"])

    if user.id == handler_id:
        if ticket.status == "in_progress":
            actions.append("complete")
        elif ticket.status == "returned":
            actions.extend(
                [
                    "edit",
                    "modify_complete",
                    "add_attachment",
                    "delete_attachment",
                ]
            )
    return actions


def _summary(ticket: Ticket) -> TicketSummary:
    return TicketSummary(
        id=ticket.id,
        ticket_no=ticket.ticket_no,
        title=ticket.title,
        type=ticket.type,
        priority=ticket.priority,
        status=ticket.status,
        is_backfilled=ticket.is_backfilled,
        created_by=_user_brief(ticket.creator),
        assignee=(
            _user_brief(ticket.assignee) if ticket.assignee else None
        ),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def ticket_to_out(ticket: Ticket, user: User) -> TicketOut:
    events = sorted(ticket.events, key=lambda event: event.created_at)
    attachments = sorted(
        ticket.attachments, key=lambda item: item.created_at
    )
    return TicketOut(
        id=ticket.id,
        ticket_no=ticket.ticket_no,
        title=ticket.title,
        type=ticket.type,
        priority=ticket.priority,
        status=ticket.status,
        is_backfilled=ticket.is_backfilled,
        created_by=_user_brief(ticket.creator),
        assignee=(
            _user_brief(ticket.assignee) if ticket.assignee else None
        ),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
        description=ticket.description,
        expected_at=ticket.expected_at,
        resolution=ticket.resolution,
        version=ticket.version,
        attachments=[_attachment_out(item) for item in attachments],
        events=[_event_out(event) for event in events],
        available_actions=_available_actions(ticket, user),
    )


def _page(page: int, page_size: int) -> tuple[int, int, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    return page, page_size, (page - 1) * page_size


def _ticket_query():
    return select(Ticket).options(
        selectinload(Ticket.creator),
        selectinload(Ticket.assignee),
        selectinload(Ticket.attachments).selectinload(
            TicketAttachment.uploader
        ),
        selectinload(Ticket.events).selectinload(TicketEvent.actor),
    )


async def _load_ticket(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    for_update: bool = False,
) -> Ticket:
    query = _ticket_query().where(Ticket.id == ticket_id)
    if for_update:
        query = query.with_for_update()
    ticket = (await db.execute(query)).scalar_one_or_none()
    if not ticket:
        raise AppError("NOT_FOUND", "工单不存在", 404)
    return ticket


async def _respond_after_commit(
    db: AsyncSession,
    ticket: Ticket,
    user: User,
) -> TicketOut:
    ticket_id = ticket.id
    await db.commit()
    db.expire(ticket)
    ticket = await _load_ticket(db, ticket_id)
    return ticket_to_out(ticket, user)


def _ensure_visible(ticket: Ticket, user: User) -> None:
    if (
        user.role != "leader"
        and ticket.created_by != user.id
        and ticket.assignee_id != user.id
    ):
        raise AppError("NOT_FOUND", "工单不存在", 404)


def _ensure_leader(user: User) -> None:
    if user.role != "leader":
        raise AppError(
            "TICKET_FORBIDDEN_ACTION", "需要领导权限", 403
        )


def _ensure_handler(ticket: Ticket, user: User) -> None:
    handler_id = ticket.assignee_id or ticket.created_by
    if handler_id != user.id:
        raise AppError(
            "TICKET_FORBIDDEN_ACTION",
            "只有当前处理人可以执行该操作",
            403,
        )


def _ensure_version(ticket: Ticket, version: int) -> None:
    if ticket.version != version:
        raise AppError(
            "CONFLICT_VERSION", "工单已被更新，请刷新后重试", 409
        )


def _ensure_status(ticket: Ticket, *statuses: str) -> None:
    if ticket.status not in statuses:
        raise AppError(
            "TICKET_INVALID_TRANSITION",
            "当前状态不允许该操作",
            409,
        )


def _touch(ticket: Ticket) -> None:
    ticket.version += 1
    ticket.updated_at = datetime.now(timezone.utc)


def _event(
    db: AsyncSession,
    ticket: Ticket,
    actor: User,
    action: str,
    from_status: str | None,
    to_status: str | None,
    comment: str | None = None,
) -> None:
    db.add(
        TicketEvent(
            ticket_id=ticket.id,
            actor_id=actor.id,
            action=action,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
        )
    )


def _validate_ticket_type(value: str) -> None:
    if value not in TICKET_TYPES:
        raise AppError(
            "VALIDATION_ERROR", "无效的工单类型", 422
        )


def _validate_priority(value: str) -> None:
    if value not in TICKET_PRIORITIES:
        raise AppError(
            "VALIDATION_ERROR", "无效的优先级", 422
        )


def _validate_attachment(filename: str, data: bytes) -> str:
    safe_name = Path(filename or "attachment").name
    if not safe_name:
        raise AppError("VALIDATION_ERROR", "附件文件名无效", 422)
    if len(safe_name) > 255:
        raise AppError(
            "VALIDATION_ERROR",
            "附件文件名不能超过 255 个字符",
            422,
        )
    if not data:
        raise AppError("VALIDATION_ERROR", "附件为空", 422)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise AppError(
            "VALIDATION_ERROR",
            f"附件不能超过 {settings.max_upload_mb}MB",
            422,
        )
    return safe_name


def _new_attachment_key(
    ticket_id: uuid.UUID, filename: str
) -> str:
    suffix = Path(filename).suffix.lower()
    return f"tickets/{ticket_id}/{uuid.uuid4().hex}{suffix}"


async def _resolve_assignee(
    db: AsyncSession,
    assignee_id: uuid.UUID | None,
) -> User:
    if not assignee_id:
        raise AppError(
            "TICKET_ASSIGNEE_REQUIRED", "必须指定处理人", 400
        )
    user = await db.get(User, assignee_id)
    if not user or user.role != "employee" or not user.is_active:
        raise AppError(
            "TICKET_ASSIGNEE_INVALID",
            "处理人不存在或不是启用中的员工",
            400,
        )
    return user


def _as_business_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(
            tzinfo=ZoneInfo(settings.business_timezone)
        )
    return value.astimezone(timezone.utc)


def _ensure_future_expected(expected_at: datetime | None) -> None:
    if (
        expected_at is not None
        and _as_business_utc(expected_at) <= datetime.now(timezone.utc)
    ):
        raise AppError(
            "VALIDATION_ERROR",
            "期望完成时间必须晚于当前时间",
            422,
        )


async def _resolve_submitter(
    db: AsyncSession,
    user: User,
    submitter_id: uuid.UUID | None,
) -> User:
    if not submitter_id or submitter_id == user.id:
        return user
    if user.role != "leader":
        raise AppError(
            "TICKET_FORBIDDEN_ACTION",
            "员工只能补录自己的工单",
            403,
        )
    submitter = await db.get(User, submitter_id)
    if (
        not submitter
        or submitter.role != "employee"
        or not submitter.is_active
    ):
        raise AppError(
            "TICKET_SUBMITTER_INVALID",
            "提交人不存在或不是启用中的员工",
            400,
        )
    return submitter


async def _next_ticket_no(db: AsyncSession) -> str:
    day = datetime.now(timezone.utc).date()
    value = (
        await db.execute(
            text(
                "INSERT INTO ticket_no_counters (day, last_value) "
                "VALUES (:day, 1) "
                "ON CONFLICT (day) DO UPDATE SET "
                "last_value = ticket_no_counters.last_value + 1 "
                "RETURNING last_value"
            ),
            {"day": day},
        )
    ).scalar_one()
    return f"T{day:%Y%m%d}-{int(value):06d}"


async def create_ticket(
    db: AsyncSession,
    user: User,
    title: str,
    description: str,
    type_: str,
    priority: str,
    expected_at: datetime | None,
    files: list[tuple[str, str | None, bytes]],
    is_backfilled: bool = False,
    backfill_created_at: datetime | None = None,
    submitter_id: uuid.UUID | None = None,
) -> TicketOut:
    title = title.strip()
    description = description.strip()
    if not title or not description:
        raise AppError(
            "VALIDATION_ERROR", "标题和描述不能为空", 422
        )
    if len(title) > 255:
        raise AppError(
            "VALIDATION_ERROR",
            "标题不能超过 255 个字符",
            422,
        )
    _validate_ticket_type(type_)
    _validate_priority(priority)
    expected_at = _as_business_utc(expected_at)

    created_at = None
    if is_backfilled:
        submitter = await _resolve_submitter(db, user, submitter_id)
        if backfill_created_at is not None:
            created = _as_business_utc(backfill_created_at)
            if created > datetime.now(timezone.utc) + timedelta(
                minutes=5
            ):
                raise AppError(
                    "VALIDATION_ERROR",
                    "原创建时间不能晚于当前时间",
                    422,
                )
            created_at = created
        status = "new"
    else:
        if submitter_id and submitter_id != user.id:
            raise AppError(
                "VALIDATION_ERROR",
                "只有补录工单可以指定提交人",
                422,
            )
        if backfill_created_at is not None:
            raise AppError(
                "VALIDATION_ERROR",
                "只有补录工单可以填写原创建时间",
                422,
            )
        _ensure_future_expected(expected_at)
        submitter = user
        status = (
            "new" if user.role == "employee" else "pending_assignment"
        )

    validated_files: list[tuple[str, str, bytes]] = []
    for filename, content_type, data in files:
        safe_name = _validate_attachment(filename, data)
        mime_type = resolve_mime_type(safe_name, content_type)
        validated_files.append((safe_name, mime_type, data))

    ticket_id = uuid.uuid4()
    uploaded: list[tuple[str, str, str, int]] = []
    uploaded_keys: list[str] = []
    try:
        for safe_name, mime_type, data in validated_files:
            object_key = _new_attachment_key(ticket_id, safe_name)
            await put_bytes_async(
                BUCKET, object_key, data, mime_type
            )
            uploaded_keys.append(object_key)
            uploaded.append(
                (object_key, safe_name, mime_type, len(data))
            )

        ticket_no = await _next_ticket_no(db)
        ticket = Ticket(
            id=ticket_id,
            ticket_no=ticket_no,
            title=title,
            description=description,
            type=type_,
            priority=priority,
            expected_at=expected_at,
            status=status,
            is_backfilled=is_backfilled,
            created_by=submitter.id,
        )
        if created_at is not None:
            ticket.created_at = created_at
        db.add(ticket)
        await db.flush()

        _event(
            db,
            ticket,
            user,
            "backfilled" if is_backfilled else "created",
            None,
            status,
        )

        for object_key, safe_name, mime_type, size_bytes in uploaded:
            db.add(
                TicketAttachment(
                    ticket_id=ticket_id,
                    object_key=object_key,
                    filename=safe_name,
                    mime_type=mime_type,
                    size_bytes=size_bytes,
                    uploaded_by=user.id,
                )
            )

        await db.commit()
    except Exception:
        await _safe_rollback(db)
        try:
            existing = (
                await db.execute(
                    select(Ticket.id).where(Ticket.id == ticket_id)
                )
            ).scalar_one_or_none()
        except Exception:
            existing = True
        if existing is None:
            for object_key in uploaded_keys:
                try:
                    await remove_object_async(BUCKET, object_key)
                except Exception:
                    logger.warning(
                        "failed to remove orphan ticket object %s",
                        object_key,
                        exc_info=True,
                    )
        raise

    db.expire(ticket)
    ticket = await _load_ticket(db, ticket_id)
    return ticket_to_out(ticket, user)


async def list_tickets(
    db: AsyncSession,
    user: User,
    status: str | None,
    type_: str | None,
    priority: str | None,
    assignee_id: uuid.UUID | None,
    keyword: str,
    date_from: datetime | None,
    date_to: datetime | None,
    page: int,
    page_size: int,
) -> TicketListResponse:
    page, page_size, offset = _page(page, page_size)
    date_from = _as_business_utc(date_from)
    date_to = _as_business_utc(date_to)
    filters = []
    if status:
        filters.append(Ticket.status == status)
    if type_:
        filters.append(Ticket.type == type_)
    if priority:
        filters.append(Ticket.priority == priority)
    if assignee_id:
        filters.append(Ticket.assignee_id == assignee_id)
    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                Ticket.title.ilike(pattern),
                Ticket.description.ilike(pattern),
                Ticket.ticket_no.ilike(pattern),
            )
        )
    if date_from:
        filters.append(Ticket.created_at >= date_from)
    if date_to:
        filters.append(Ticket.created_at <= date_to)
    if user.role != "leader":
        filters.append(
            or_(
                Ticket.created_by == user.id,
                Ticket.assignee_id == user.id,
            )
        )

    count_query = select(func.count()).select_from(Ticket)
    query = select(Ticket).options(
        selectinload(Ticket.creator),
        selectinload(Ticket.assignee),
    )
    if filters:
        count_query = count_query.where(*filters)
        query = query.where(*filters)

    total = (await db.execute(count_query)).scalar_one()
    tickets = (
        await db.execute(
            query.order_by(Ticket.updated_at.desc())
            .offset(offset)
            .limit(page_size)
        )
    ).scalars().all()
    return TicketListResponse(
        items=[_summary(ticket) for ticket in tickets],
        total=total,
        page=page,
        page_size=page_size,
    )


async def ticket_detail(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
) -> TicketOut:
    ticket = await _load_ticket(db, ticket_id)
    _ensure_visible(ticket, user)
    return ticket_to_out(ticket, user)


async def approve_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    payload,
) -> TicketOut:
    _ensure_leader(user)
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_version(ticket, payload.version)
    from_status = ticket.status

    if ticket.is_backfilled:
        _ensure_status(ticket, "new", "modified")
        ticket.status = "resolved"
        action = "approved"
    elif ticket.status == "new":
        assignee = await _resolve_assignee(
            db, payload.assignee_id or ticket.created_by
        )
        ticket.assignee_id = assignee.id
        ticket.status = "in_progress"
        action = "approved"
    elif ticket.status == "completed":
        ticket.status = "resolved"
        action = "approved"
    elif ticket.status == "modified":
        if payload.assignee_id:
            assignee = await _resolve_assignee(
                db, payload.assignee_id
            )
            ticket.assignee_id = assignee.id
        elif not ticket.assignee_id:
            assignee = await _resolve_assignee(
                db, ticket.created_by
            )
            ticket.assignee_id = assignee.id
        ticket.status = "in_progress"
        action = "approved"
    else:
        raise AppError(
            "TICKET_INVALID_TRANSITION",
            "当前状态不允许审核通过",
            409,
        )

    _event(
        db,
        ticket,
        user,
        action,
        from_status,
        ticket.status,
        payload.comment,
    )
    _touch(ticket)
    return await _respond_after_commit(db, ticket, user)


async def reject_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    payload: RejectRequest,
) -> TicketOut:
    _ensure_leader(user)
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_version(ticket, payload.version)
    _ensure_status(ticket, "new", "completed", "modified")
    from_status = ticket.status
    ticket.status = "returned"
    _event(
        db,
        ticket,
        user,
        "rejected",
        from_status,
        ticket.status,
        payload.comment,
    )
    _touch(ticket)
    return await _respond_after_commit(db, ticket, user)


async def assign_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    payload: AssignRequest,
) -> TicketOut:
    _ensure_leader(user)
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_version(ticket, payload.version)
    _ensure_status(ticket, "pending_assignment")
    assignee = await _resolve_assignee(db, payload.assignee_id)
    from_status = ticket.status
    ticket.assignee_id = assignee.id
    ticket.status = "in_progress"
    _event(
        db,
        ticket,
        user,
        "assigned",
        from_status,
        ticket.status,
        None,
    )
    _touch(ticket)
    return await _respond_after_commit(db, ticket, user)


async def complete_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    payload: CompleteRequest,
) -> TicketOut:
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_version(ticket, payload.version)
    _ensure_status(ticket, "in_progress")
    _ensure_handler(ticket, user)
    from_status = ticket.status
    ticket.resolution = payload.resolution
    ticket.status = (
        "completed"
        if ticket.creator.role == "employee"
        else "pending_user_confirmation"
    )
    _event(
        db,
        ticket,
        user,
        "marked_completed",
        from_status,
        ticket.status,
        payload.resolution,
    )
    _touch(ticket)
    return await _respond_after_commit(db, ticket, user)


async def modify_complete_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    payload: ModifyCompleteRequest,
) -> TicketOut:
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_version(ticket, payload.version)
    _ensure_status(ticket, "returned")
    _ensure_handler(ticket, user)
    from_status = ticket.status
    ticket.status = "modified"
    _event(
        db,
        ticket,
        user,
        "marked_modified",
        from_status,
        ticket.status,
        payload.comment,
    )
    _touch(ticket)
    return await _respond_after_commit(db, ticket, user)


async def confirm_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    payload: ConfirmRequest,
) -> TicketOut:
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    if user.role != "leader" or user.id != ticket.created_by:
        raise AppError(
            "TICKET_FORBIDDEN_ACTION",
            "只有提交该工单的领导可以确认",
            403,
        )
    _ensure_version(ticket, payload.version)
    _ensure_status(ticket, "pending_user_confirmation")
    from_status = ticket.status
    if payload.resolved:
        ticket.status = "resolved"
        action = "confirmed_resolved"
    else:
        if not (payload.comment or "").strip():
            raise AppError(
                "VALIDATION_ERROR", "未解决时必须填写说明", 422
            )
        ticket.status = "returned"
        action = "confirmed_unresolved"
    _event(
        db,
        ticket,
        user,
        action,
        from_status,
        ticket.status,
        payload.comment,
    )
    _touch(ticket)
    return await _respond_after_commit(db, ticket, user)


async def edit_ticket(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
) -> TicketOut:
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_version(ticket, payload.version)
    _ensure_status(ticket, "returned")
    _ensure_handler(ticket, user)

    changed = False
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise AppError(
                "VALIDATION_ERROR", "标题不能为空", 422
            )
        ticket.title = title
        changed = True
    if payload.description is not None:
        description = payload.description.strip()
        if not description:
            raise AppError(
                "VALIDATION_ERROR", "描述不能为空", 422
            )
        ticket.description = description
        changed = True
    if payload.type is not None:
        _validate_ticket_type(payload.type)
        ticket.type = payload.type
        changed = True
    if payload.priority is not None:
        _validate_priority(payload.priority)
        ticket.priority = payload.priority
        changed = True
    if payload.expected_at is not None:
        ticket.expected_at = _as_business_utc(payload.expected_at)
        changed = True
    if not changed:
        raise AppError(
            "VALIDATION_ERROR", "至少修改一个字段", 422
        )

    _event(
        db,
        ticket,
        user,
        "edited",
        ticket.status,
        ticket.status,
        None,
    )
    _touch(ticket)
    return await _respond_after_commit(db, ticket, user)


async def add_attachment(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    filename: str,
    content_type: str | None,
    data: bytes,
) -> TicketAttachmentOut:
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_visible(ticket, user)
    _ensure_status(ticket, "returned")
    _ensure_handler(ticket, user)
    safe_name = _validate_attachment(filename, data)
    object_key = _new_attachment_key(ticket.id, safe_name)
    mime_type = resolve_mime_type(safe_name, content_type)
    await put_bytes_async(BUCKET, object_key, data, mime_type)
    attachment_id = uuid.uuid4()
    attachment = TicketAttachment(
        id=attachment_id,
        ticket_id=ticket.id,
        object_key=object_key,
        filename=safe_name,
        mime_type=mime_type,
        size_bytes=len(data),
        uploaded_by=user.id,
    )
    try:
        db.add(attachment)
        await db.commit()
    except Exception:
        await _safe_rollback(db)
        try:
            existing = (
                await db.execute(
                    select(TicketAttachment.id).where(
                        TicketAttachment.id == attachment_id
                    )
                )
            ).scalar_one_or_none()
        except Exception:
            existing = True
        if existing is None:
            try:
                await remove_object_async(BUCKET, object_key)
            except Exception:
                logger.warning(
                    "failed to remove orphan attachment %s",
                    object_key,
                    exc_info=True,
                )
        raise
    await db.refresh(attachment)
    return TicketAttachmentOut(
        id=attachment.id,
        filename=attachment.filename,
        mime_type=attachment.mime_type,
        size_bytes=attachment.size_bytes,
        uploaded_by=_user_brief(user),
        created_at=attachment.created_at,
    )


async def _load_attachment(
    db: AsyncSession,
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> TicketAttachment:
    attachment = (
        await db.execute(
            select(TicketAttachment).where(
                TicketAttachment.id == attachment_id,
                TicketAttachment.ticket_id == ticket_id,
            )
        )
    ).scalar_one_or_none()
    if not attachment:
        raise AppError("NOT_FOUND", "附件不存在", 404)
    return attachment


async def delete_attachment(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> None:
    ticket = await _load_ticket(db, ticket_id, for_update=True)
    _ensure_visible(ticket, user)
    _ensure_status(ticket, "returned")
    _ensure_handler(ticket, user)
    attachment = await _load_attachment(
        db, ticket_id, attachment_id
    )
    await remove_object_async(BUCKET, attachment.object_key)
    await db.delete(attachment)
    await db.commit()


async def attachment_download(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> AttachmentDownloadResponse:
    ticket = await _load_ticket(db, ticket_id)
    _ensure_visible(ticket, user)
    attachment = await _load_attachment(
        db, ticket_id, attachment_id
    )
    return AttachmentDownloadResponse(
        download_url=(
            f"{settings.public_api_url}/api/v1/tickets/"
            f"{ticket.id}/attachments/{attachment.id}/download/file"
        ),
        expires_in=600,
    )


async def attachment_file(
    db: AsyncSession,
    user: User,
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
) -> tuple[TicketAttachment, bytes]:
    ticket = await _load_ticket(db, ticket_id)
    _ensure_visible(ticket, user)
    attachment = await _load_attachment(
        db, ticket_id, attachment_id
    )
    data = await get_bytes_async(BUCKET, attachment.object_key)
    return attachment, data
