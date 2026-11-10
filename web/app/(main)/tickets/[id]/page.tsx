"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import {
  BackfilledBadge,
  TicketPriorityBadge,
  TicketStatusBadge,
  TicketTypeBadge,
} from "@/components/status-badge";
import {
  Button,
  ButtonSecondary,
  Card,
  Dialog,
  ErrorState,
  Input,
  PageHeader,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { ApiError, apiFetch, apiUpload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  DownloadResult,
  TicketAttachment,
  TicketDetail,
  UserBrief,
} from "@/lib/types";
import {
  TICKET_ACTION_LABEL,
  TICKET_EVENT_LABEL,
  TICKET_PRIORITY_LABEL,
  TICKET_STATUS_LABEL,
  TICKET_TYPE_LABEL,
  formatBytes,
  formatDate,
} from "@/lib/utils";

function toLocalInput(value: string | null): string {
  if (!value) {
    return "";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  const offset = date.getTimezoneOffset();
  const local = new Date(date.getTime() - offset * 60000);
  return local.toISOString().slice(0, 16);
}

export default function TicketDetailPage() {
  const params = useParams<{ id: string }>();
  const ticketId = params.id;
  const { user } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const isLeader = user?.role === "leader";

  const ticketQuery = useQuery({
    queryKey: ["ticket", ticketId],
    queryFn: () => apiFetch<TicketDetail>(`/tickets/${ticketId}`),
    enabled: Boolean(user && ticketId),
  });

  const employeesQuery = useQuery({
    queryKey: ["users", "employees"],
    queryFn: () =>
      apiFetch<{ items: UserBrief[] }>("/users?role=employee"),
    enabled: Boolean(isLeader),
  });

  const [action, setAction] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [resolution, setResolution] = useState("");
  const [editTitle, setEditTitle] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editType, setEditType] = useState("it_fault");
  const [editPriority, setEditPriority] = useState("medium");
  const [editExpectedAt, setEditExpectedAt] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const ticket = ticketQuery.data;
  const employees = employeesQuery.data?.items ?? [];

  function openAction(next: string) {
    if (!ticket) {
      return;
    }
    setAction(next);
    setComment("");
    setResolution(ticket.resolution ?? "");
    setAssigneeId(ticket.assignee?.id ?? "");
    setEditTitle(ticket.title);
    setEditDescription(ticket.description);
    setEditType(ticket.type);
    setEditPriority(ticket.priority);
    setEditExpectedAt(toLocalInput(ticket.expected_at));
    setFile(null);
    setError("");
    setNotice("");
  }

  const actionMutation = useMutation({
    mutationFn: async () => {
      if (!ticket || !action) {
        throw new Error("没有选中的操作");
      }
      if (action === "edit") {
        if (!editTitle.trim() || !editDescription.trim()) {
          throw new Error("标题和描述不能为空");
        }
        return apiFetch<TicketDetail>(`/tickets/${ticket.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            version: ticket.version,
            title: editTitle.trim(),
            description: editDescription.trim(),
            type: editType,
            priority: editPriority,
            expected_at: editExpectedAt
              ? new Date(editExpectedAt).toISOString()
              : undefined,
          }),
        });
      }
      if (action === "add_attachment") {
        if (!file) {
          throw new Error("请选择附件");
        }
        const form = new FormData();
        form.append("file", file);
        return apiUpload<TicketAttachment>(
          `/tickets/${ticket.id}/attachments`,
          form,
        );
      }

      const body: Record<string, unknown> = {
        version: ticket.version,
      };
      if (action === "approve") {
        if (assigneeId) {
          body.assignee_id = assigneeId;
        }
        if (comment.trim()) {
          body.comment = comment.trim();
        }
      } else if (action === "reject") {
        if (!comment.trim()) {
          throw new Error("驳回必须填写原因");
        }
        body.comment = comment.trim();
      } else if (action === "assign") {
        if (!assigneeId) {
          throw new Error("请选择处理人");
        }
        body.assignee_id = assigneeId;
      } else if (action === "complete") {
        if (resolution.trim()) {
          body.resolution = resolution.trim();
        }
      } else if (action === "modify_complete") {
        if (comment.trim()) {
          body.comment = comment.trim();
        }
      } else if (
        action === "confirm_resolved" ||
        action === "confirm_unresolved"
      ) {
        body.resolved = action === "confirm_resolved";
        if (comment.trim()) {
          body.comment = comment.trim();
        }
        if (
          action === "confirm_unresolved" &&
          !comment.trim()
        ) {
          throw new Error("确认未解决必须填写原因");
        }
      }

      const endpoints: Record<string, string> = {
        approve: "approve",
        reject: "reject",
        assign: "assign",
        complete: "complete",
        modify_complete: "modify-complete",
        confirm_resolved: "confirm",
        confirm_unresolved: "confirm",
      };
      return apiFetch<TicketDetail>(
        `/tickets/${ticket.id}/${endpoints[action]}`,
        {
          method: "POST",
          body: JSON.stringify(body),
        },
      );
    },
    onSuccess: () => {
      setNotice("操作成功");
      setAction(null);
      void queryClient.invalidateQueries({
        queryKey: ["ticket", ticketId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["tickets"],
      });
    },
    onError: (err) => {
      setError(err instanceof Error ? err.message : "操作失败");
      if (
        err instanceof ApiError &&
        err.code === "CONFLICT_VERSION"
      ) {
        void queryClient.invalidateQueries({
          queryKey: ["ticket", ticketId],
        });
      }
    },
  });

  const deleteAttachmentMutation = useMutation({
    mutationFn: (attachmentId: string) =>
      apiFetch<void>(
        `/tickets/${ticketId}/attachments/${attachmentId}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      setNotice("附件已删除");
      void queryClient.invalidateQueries({
        queryKey: ["ticket", ticketId],
      });
    },
    onError: (err) =>
      setError(
        err instanceof Error ? err.message : "删除附件失败",
      ),
  });

  async function downloadAttachment(
    attachment: TicketAttachment,
  ) {
    try {
      const result = await apiFetch<DownloadResult>(
        `/tickets/${ticketId}/attachments/${attachment.id}/download`,
      );
      window.open(result.download_url, "_blank");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "下载附件失败",
      );
    }
  }

  if (ticketQuery.isLoading) {
    return <Spinner label="加载工单" />;
  }
  if (ticketQuery.isError || !ticket) {
    return (
      <ErrorState
        message={
          ticketQuery.error instanceof Error
            ? ticketQuery.error.message
            : "加载工单失败"
        }
        onRetry={() => void ticketQuery.refetch()}
      />
    );
  }

  const actionable = ticket.available_actions.filter(
    (item) =>
      item !== "delete_attachment" && item !== "add_attachment",
  );
  const confirmDisabled =
    actionMutation.isPending ||
    ((action === "reject" ||
      action === "confirm_unresolved") &&
      !comment.trim()) ||
    (action === "assign" && !assigneeId) ||
    (action === "add_attachment" && !file) ||
    (action === "edit" &&
      (!editTitle.trim() || !editDescription.trim()));

  return (
    <div>
      <PageHeader
        title={ticket.title}
        description={ticket.ticket_no}
        action={
          <ButtonSecondary onClick={() => router.push("/tickets")}>
            返回列表
          </ButtonSecondary>
        }
      />

      {notice ? (
        <div className="mb-4 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-700">
          {notice}
        </div>
      ) : null}
      {error ? (
        <div className="mb-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-2">
        <TicketStatusBadge status={ticket.status} />
        <TicketPriorityBadge priority={ticket.priority} />
        <TicketTypeBadge type={ticket.type} />
        {ticket.is_backfilled ? <BackfilledBadge /> : null}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              描述
            </h2>
            <p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">
              {ticket.description}
            </p>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              附件
            </h2>
            {ticket.attachments.length === 0 ? (
              <p className="mt-2 text-sm text-slate-500">
                没有附件
              </p>
            ) : (
              <div className="mt-3 space-y-2">
                {ticket.attachments.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="flex items-center justify-between gap-2 rounded-md border border-slate-200 p-2 text-sm"
                  >
                    <div className="min-w-0">
                      <div className="truncate font-medium text-slate-800">
                        {attachment.filename}
                      </div>
                      <div className="text-xs text-slate-500">
                        {formatBytes(attachment.size_bytes)} ·{" "}
                        {attachment.uploaded_by.display_name} ·{" "}
                        {formatDate(attachment.created_at)}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <ButtonSecondary
                        className="px-2 py-1 text-xs"
                        onClick={() =>
                          void downloadAttachment(attachment)
                        }
                      >
                        下载
                      </ButtonSecondary>
                      {ticket.available_actions.includes(
                        "delete_attachment",
                      ) ? (
                        <ButtonSecondary
                          className="px-2 py-1 text-xs"
                          onClick={() => {
                            if (
                              window.confirm(
                                "确定删除该附件吗？",
                              )
                            ) {
                              deleteAttachmentMutation.mutate(
                                attachment.id,
                              );
                            }
                          }}
                        >
                          删除
                        </ButtonSecondary>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
            )}
            {ticket.available_actions.includes(
              "add_attachment",
            ) ? (
              <div className="mt-3">
                <ButtonSecondary
                  onClick={() => openAction("add_attachment")}
                >
                  添加附件
                </ButtonSecondary>
              </div>
            ) : null}
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              时间线
            </h2>
            <div className="mt-3 space-y-3">
              {ticket.events.map((event) => (
                <div
                  key={event.id}
                  className="border-l-2 border-slate-200 pl-3 text-sm"
                >
                  <div className="font-medium text-slate-800">
                    {TICKET_EVENT_LABEL[event.action] ??
                      event.action}
                  </div>
                  <div className="text-xs text-slate-500">
                    {event.actor.display_name} ·{" "}
                    {formatDate(event.created_at)}
                  </div>
                  <div className="text-xs text-slate-500">
                    {event.from_status
                      ? TICKET_STATUS_LABEL[event.from_status] ??
                        event.from_status
                      : "—"}{" "}
                    →{" "}
                    {event.to_status
                      ? TICKET_STATUS_LABEL[event.to_status] ??
                        event.to_status
                      : "—"}
                  </div>
                  {event.comment ? (
                    <p className="mt-1 text-sm text-slate-600">
                      {event.comment}
                    </p>
                  ) : null}
                </div>
              ))}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              基本信息
            </h2>
            <dl className="mt-3 space-y-2 text-sm">
              <div>
                <dt className="text-xs text-slate-500">提交人</dt>
                <dd className="text-slate-900">
                  {ticket.created_by.display_name}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">处理人</dt>
                <dd className="text-slate-900">
                  {ticket.assignee?.display_name ?? "未指派"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">
                  期望完成时间
                </dt>
                <dd className="text-slate-900">
                  {formatDate(ticket.expected_at)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">
                  创建时间
                </dt>
                <dd className="text-slate-900">
                  {formatDate(ticket.created_at)}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">
                  更新时间
                </dt>
                <dd className="text-slate-900">
                  {formatDate(ticket.updated_at)}
                </dd>
              </div>
              {ticket.resolution ? (
                <div>
                  <dt className="text-xs text-slate-500">
                    处理说明
                  </dt>
                  <dd className="whitespace-pre-wrap text-slate-900">
                    {ticket.resolution}
                  </dd>
                </div>
              ) : null}
            </dl>
          </Card>

          <Card>
            <h2 className="text-sm font-semibold text-slate-900">
              操作
            </h2>
            <div className="mt-3 flex flex-wrap gap-2">
              {actionable.map((item) => (
                <Button
                  key={item}
                  onClick={() => openAction(item)}
                >
                  {TICKET_ACTION_LABEL[item] ?? item}
                </Button>
              ))}
              {actionable.length === 0 ? (
                <p className="text-sm text-slate-500">
                  当前没有可执行操作。
                </p>
              ) : null}
            </div>
            {ticket.available_actions.includes(
              "add_attachment",
            ) ? (
              <p className="mt-2 text-xs text-slate-500">
                附件操作在上方“附件”卡片。
              </p>
            ) : null}
          </Card>
        </div>
      </div>

      <Dialog
        open={Boolean(action)}
        title={action ? TICKET_ACTION_LABEL[action] ?? action : ""}
        onClose={() => setAction(null)}
      >
        {action ? (
          <div className="space-y-4">
            {[
              "approve",
              "reject",
              "modify_complete",
              "confirm_resolved",
              "confirm_unresolved",
            ].includes(action) ? (
              <Textarea
                rows={4}
                placeholder={
                  action === "reject" ||
                  action === "confirm_unresolved"
                    ? "请填写原因（必填）"
                    : "审批意见（可选）"
                }
                value={comment}
                onChange={(event) =>
                  setComment(event.target.value)
                }
              />
            ) : null}

            {action === "approve" &&
            !ticket.is_backfilled &&
            (ticket.status === "new" ||
              (ticket.status === "modified" &&
                !ticket.assignee)) ? (
              <div>
                <label className="mb-1 block text-sm text-slate-600">
                  处理人
                </label>
                <Select
                  value={assigneeId}
                  onChange={(event) =>
                    setAssigneeId(event.target.value)
                  }
                >
                  <option value="">
                    默认提交人（
                    {ticket.created_by.display_name}）
                  </option>
                  {employees.map((employee) => (
                    <option
                      key={employee.id}
                      value={employee.id}
                    >
                      {employee.display_name}
                    </option>
                  ))}
                </Select>
              </div>
            ) : null}

            {action === "approve" && ticket.is_backfilled ? (
              <p className="text-xs text-slate-500">
                补录工单审核通过后直接变为「已解决」。
              </p>
            ) : null}

            {action === "assign" ? (
              <div>
                <label className="mb-1 block text-sm text-slate-600">
                  处理人
                </label>
                <Select
                  value={assigneeId}
                  onChange={(event) =>
                    setAssigneeId(event.target.value)
                  }
                >
                  <option value="">请选择处理人</option>
                  {employees.map((employee) => (
                    <option
                      key={employee.id}
                      value={employee.id}
                    >
                      {employee.display_name}
                    </option>
                  ))}
                </Select>
              </div>
            ) : null}

            {action === "complete" ? (
              <Textarea
                rows={3}
                placeholder="处理说明（可选）"
                value={resolution}
                onChange={(event) =>
                  setResolution(event.target.value)
                }
              />
            ) : null}

            {action === "edit" ? (
              <div className="space-y-3">
                <Input
                  value={editTitle}
                  maxLength={255}
                  onChange={(event) =>
                    setEditTitle(event.target.value)
                  }
                  placeholder="标题"
                />
                <Textarea
                  rows={4}
                  value={editDescription}
                  onChange={(event) =>
                    setEditDescription(event.target.value)
                  }
                  placeholder="描述"
                />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Select
                    value={editType}
                    onChange={(event) =>
                      setEditType(event.target.value)
                    }
                  >
                    {Object.entries(TICKET_TYPE_LABEL).map(
                      ([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ),
                    )}
                  </Select>
                  <Select
                    value={editPriority}
                    onChange={(event) =>
                      setEditPriority(event.target.value)
                    }
                  >
                    {Object.entries(TICKET_PRIORITY_LABEL).map(
                      ([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ),
                    )}
                  </Select>
                </div>
                <Input
                  type="datetime-local"
                  value={editExpectedAt}
                  onChange={(event) =>
                    setEditExpectedAt(event.target.value)
                  }
                />
              </div>
            ) : null}

            {action === "add_attachment" ? (
              <Input
                type="file"
                onChange={(event) =>
                  setFile(event.target.files?.[0] ?? null)
                }
              />
            ) : null}

            <div className="flex justify-end gap-2">
              <ButtonSecondary
                type="button"
                onClick={() => setAction(null)}
              >
                取消
              </ButtonSecondary>
              <Button
                disabled={confirmDisabled}
                onClick={() => {
                  setError("");
                  setNotice("");
                  actionMutation.mutate();
                }}
              >
                {actionMutation.isPending ? "提交中..." : "确认"}
              </Button>
            </div>
          </div>
        ) : null}
      </Dialog>
    </div>
  );
}
