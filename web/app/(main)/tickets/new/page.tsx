"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import {
  Button,
  ButtonSecondary,
  Card,
  ErrorState,
  Input,
  PageHeader,
  Select,
  Textarea,
} from "@/components/ui";
import { apiFetch, apiUpload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TicketDetail, UserBrief } from "@/lib/types";
import {
  TICKET_PRIORITY_LABEL,
  TICKET_TYPE_LABEL,
} from "@/lib/utils";

function localDateTimeValue(date: Date): string {
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60000)
    .toISOString()
    .slice(0, 16);
}

export default function NewTicketPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("it_fault");
  const [priority, setPriority] = useState("medium");
  const [expectedAt, setExpectedAt] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isBackfilled, setIsBackfilled] = useState(false);
  const [backfillCreatedAt, setBackfillCreatedAt] = useState("");
  const [submitterId, setSubmitterId] = useState("");
  const [error, setError] = useState("");

  const isLeader = user?.role === "leader";
  const nowLocal = localDateTimeValue(new Date());

  const employeesQuery = useQuery({
    queryKey: ["users", "employees"],
    queryFn: () =>
      apiFetch<{ items: UserBrief[] }>("/users?role=employee"),
    enabled: Boolean(isLeader && isBackfilled),
  });

  const createMutation = useMutation({
    mutationFn: async () => {
      if (!title.trim() || !description.trim()) {
        throw new Error("标题和描述不能为空");
      }
      if (!isBackfilled && expectedAt) {
        if (new Date(expectedAt).getTime() <= Date.now()) {
          throw new Error("期望完成时间必须晚于当前时间");
        }
      }
      if (
        isBackfilled &&
        backfillCreatedAt &&
        new Date(backfillCreatedAt).getTime() > Date.now()
      ) {
        throw new Error("原创建时间不能晚于当前时间");
      }
      const form = new FormData();
      form.append("title", title.trim());
      form.append("description", description.trim());
      form.append("type", type);
      form.append("priority", priority);
      form.append("is_backfilled", isBackfilled ? "true" : "false");
      if (expectedAt) {
        form.append(
          "expected_at",
          new Date(expectedAt).toISOString(),
        );
      }
      if (isBackfilled && backfillCreatedAt) {
        form.append(
          "backfill_created_at",
          new Date(backfillCreatedAt).toISOString(),
        );
      }
      if (isBackfilled && isLeader && submitterId) {
        form.append("submitter_id", submitterId);
      }
      for (const file of files) {
        form.append("files", file);
      }
      return apiUpload<TicketDetail>("/tickets", form);
    },
    onSuccess: (ticket) => router.push(`/tickets/${ticket.id}`),
    onError: (err) =>
      setError(
        err instanceof Error ? err.message : "创建工单失败",
      ),
  });

  const employees = employeesQuery.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title="新建工单"
        description="提交后按角色进入审核、补录或待分配流程。"
        action={
          <ButtonSecondary onClick={() => router.push("/tickets")}>
            返回列表
          </ButtonSecondary>
        }
      />

      {error ? (
        <div className="mb-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      <Card>
        <form
          className="space-y-4"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            setError("");
            createMutation.mutate();
          }}
        >
          <div>
            <label className="mb-1 block text-sm text-slate-600">
              标题
            </label>
            <Input
              value={title}
              maxLength={255}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="例如：无法连接公司 VPN"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">
              描述
            </label>
            <Textarea
              rows={5}
              value={description}
              onChange={(event) =>
                setDescription(event.target.value)
              }
              placeholder="请描述问题、现象、已尝试的操作"
            />
          </div>

          <div className="rounded-md border border-amber-200 bg-amber-50 p-3">
            <label className="flex items-start gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                className="mt-1"
                checked={isBackfilled}
                onChange={(event) =>
                  setIsBackfilled(event.target.checked)
                }
              />
              <span>
                <span className="font-medium">补录历史工单</span>
                <span className="mt-1 block text-xs text-slate-500">
                  {isBackfilled
                    ? "用于补录已经完成的历史工单；创建后由领导审核，通过即视为已解决。"
                    : "勾选后可以填写过去的原创建时间和期望完成时间。"}
                </span>
              </span>
            </label>
            {isBackfilled ? (
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm text-slate-600">
                    原创建时间（可选）
                  </label>
                  <Input
                    type="datetime-local"
                    max={nowLocal}
                    value={backfillCreatedAt}
                    onChange={(event) =>
                      setBackfillCreatedAt(event.target.value)
                    }
                  />
                </div>
                {isLeader ? (
                  <div>
                    <label className="mb-1 block text-sm text-slate-600">
                      提交人
                    </label>
                    <Select
                      value={submitterId}
                      onChange={(event) =>
                        setSubmitterId(event.target.value)
                      }
                    >
                      <option value="">
                        我自己（{user?.display_name}）
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
              </div>
            ) : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm text-slate-600">
                类型
              </label>
              <Select
                value={type}
                onChange={(event) => setType(event.target.value)}
              >
                {Object.entries(TICKET_TYPE_LABEL).map(
                  ([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ),
                )}
              </Select>
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-600">
                优先级
              </label>
              <Select
                value={priority}
                onChange={(event) =>
                  setPriority(event.target.value)
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
            <div>
              <label className="mb-1 block text-sm text-slate-600">
                期望完成时间
              </label>
              <Input
                type="datetime-local"
                min={isBackfilled ? undefined : nowLocal}
                value={expectedAt}
                onChange={(event) =>
                  setExpectedAt(event.target.value)
                }
              />
              <p className="mt-1 text-xs text-slate-500">
                {isBackfilled
                  ? "补录工单可以选择过去的时间。"
                  : "正常工单必须晚于当前时间。"}
              </p>
            </div>
            <div>
              <label className="mb-1 block text-sm text-slate-600">
                附件
              </label>
              <Input
                type="file"
                multiple
                onChange={(event) =>
                  setFiles(
                    Array.from(event.target.files ?? []),
                  )
                }
              />
            </div>
          </div>
          <p className="text-xs text-slate-500">
            {isBackfilled
              ? "补录工单创建后进入新建状态，由领导审核；审核通过后直接变为已解决。"
              : user?.role === "leader"
                ? "领导提交后进入待分配，需指派处理人。"
                : "员工提交后由领导审核，审核通过后进入处理中。"}
          </p>
          <div className="flex justify-end gap-2">
            <ButtonSecondary
              type="button"
              onClick={() => router.push("/tickets")}
            >
              取消
            </ButtonSecondary>
            <Button disabled={createMutation.isPending}>
              {createMutation.isPending ? "提交中..." : "提交工单"}
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
