"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import Link from "next/link";
import { useRef, useState } from "react";

import {
  Button,
  ButtonSecondary,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  TableSkeleton,
  Textarea,
} from "@/components/ui";
import { API_BASE, apiFetch, apiUpload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  EvalDataset,
  EvalPermission,
  EvalRun,
} from "@/lib/types";
import {
  EVAL_MODE_LABEL,
  EVAL_RUN_STATUS_LABEL,
  formatDate,
  formatPercent,
} from "@/lib/utils";

function formatConfigShort(
  config?: Record<string, unknown> | null,
): string {
  if (!config) return "默认";
  const flags = [
    config.hybrid_enabled ? "混合" : null,
    config.rerank_enabled ? "精排" : null,
    config.rewrite_enabled ? "改写" : null,
  ].filter(Boolean);
  return flags.length ? flags.join("+") : "稠密";
}

export default function EvaluationsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isLeader = user?.role === "leader";
  const canEvaluate = isLeader || Boolean(user?.can_evaluate);

  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const datasetsQuery = useQuery({
    queryKey: ["eval", "datasets"],
    queryFn: () => apiFetch<{ items: EvalDataset[] }>("/eval/datasets"),
    enabled: canEvaluate,
  });

  const runsQuery = useQuery({
    queryKey: ["eval", "runs", "recent"],
    queryFn: () => apiFetch<{ items: EvalRun[] }>("/eval/runs?limit=10"),
    enabled: canEvaluate,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) {
        return false;
      }
      const active = data.items.some(
        (run) => run.status === "pending" || run.status === "running",
      );
      return active ? 3000 : false;
    },
  });

  const permissionsQuery = useQuery({
    queryKey: ["eval", "permissions"],
    queryFn: () =>
      apiFetch<{ items: EvalPermission[] }>("/eval/permissions"),
    enabled: isLeader,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["eval"] });
  };

  const createMutation = useMutation({
    mutationFn: () =>
      apiFetch<EvalDataset>("/eval/datasets", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() || null,
        }),
      }),
    onSuccess: (dataset) => {
      setCreateOpen(false);
      setName("");
      setDescription("");
      setNotice(`数据集「${dataset.name}」已创建`);
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "创建失败"),
  });

  const importMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return apiUpload<{
        dataset_id: string;
        imported_cases: number;
        imported_turns: number;
      }>("/eval/import", form);
    },
    onSuccess: (result) => {
      setNotice(
        `导入成功：${result.imported_cases} 个用例，${result.imported_turns} 个轮次`,
      );
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "导入失败"),
  });

  const permissionMutation = useMutation({
    mutationFn: ({
      userId,
      enabled,
    }: {
      userId: string;
      enabled: boolean;
    }) =>
      apiFetch<EvalPermission>(`/eval/permissions/${userId}`, {
        method: "PATCH",
        body: JSON.stringify({ can_evaluate: enabled }),
      }),
    onSuccess: () => {
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "权限更新失败"),
  });

  const archiveMutation = useMutation({
    mutationFn: (id: string) =>
      apiFetch<EvalDataset>(`/eval/datasets/${id}`, {
        method: "DELETE",
      }),
    onSuccess: () => {
      setNotice("数据集已归档");
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "归档失败"),
  });

  if (!canEvaluate) {
    return (
      <ErrorState message="没有评测权限，请联系领导开通。" />
    );
  }

  const datasets = datasetsQuery.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title="评测"
        description="RAG 问答回归评测：数据集、运行记录与指标对比"
        action={
          <div className="flex gap-2">
            <input
              ref={fileRef}
              type="file"
              accept=".jsonl,application/jsonl,text/plain"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  setError("");
                  setNotice("");
                  importMutation.mutate(file);
                }
                event.target.value = "";
              }}
            />
            <ButtonSecondary
              onClick={() => {
                setError("");
                setNotice("");
                fileRef.current?.click();
              }}
              disabled={importMutation.isPending}
            >
              {importMutation.isPending ? "导入中..." : "导入 JSONL"}
            </ButtonSecondary>
            <Button onClick={() => setCreateOpen(true)}>新建数据集</Button>
          </div>
        }
      />

      {notice ? (
        <p className="mb-4 rounded-md bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
          {notice}
        </p>
      ) : null}
      {error ? (
        <div className="mb-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-slate-900">
          数据集
        </h2>
        {datasetsQuery.isLoading ? (
          <TableSkeleton rows={4} columns={5} />
        ) : datasetsQuery.error ? (
          <ErrorState
            message={
              datasetsQuery.error instanceof Error
                ? datasetsQuery.error.message
                : "加载失败"
            }
            onRetry={() => void datasetsQuery.refetch()}
          />
        ) : datasets.length === 0 ? (
          <EmptyState
            title="还没有评测数据集"
            description="新建数据集，或导入 JSONL 草稿"
          />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">名称</th>
                  <th className="px-4 py-3">用例</th>
                  <th className="px-4 py-3">轮次</th>
                  <th className="px-4 py-3">最近运行</th>
                  <th className="px-4 py-3">操作</th>
                </tr>
              </thead>
              <tbody>
                {datasets.map((dataset) => (
                  <tr
                    key={dataset.id}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/evaluations/${dataset.id}`}
                        className="font-medium text-slate-900 hover:underline"
                      >
                        {dataset.name}
                      </Link>
                      <p className="mt-1 text-xs text-slate-500">
                        {dataset.description || "无说明"}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {dataset.case_count}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {dataset.turn_count}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {dataset.last_run ? (
                        <Link
                          href={`/evaluations/runs/${dataset.last_run.id}`}
                          className="hover:underline"
                        >
                          {EVAL_RUN_STATUS_LABEL[dataset.last_run.status]}{" "}
                          {formatDate(dataset.last_run.created_at)}
                        </Link>
                      ) : (
                        "从未运行"
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-2">
                        <Link
                          href={`/evaluations/${dataset.id}`}
                          className="text-slate-600 hover:underline"
                        >
                          进入
                        </Link>
                        <a
                          href={`${API_BASE}/eval/datasets/${dataset.id}/export`}
                          className="text-slate-600 hover:underline"
                        >
                          导出
                        </a>
                        <button
                          className="text-red-600 hover:underline"
                          onClick={() => {
                            if (
                              window.confirm(
                                `确认归档数据集「${dataset.name}」？`,
                              )
                            ) {
                              archiveMutation.mutate(dataset.id);
                            }
                          }}
                        >
                          归档
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-slate-900">
          最近运行
        </h2>
        {runsQuery.isLoading ? (
          <TableSkeleton rows={3} columns={6} />
        ) : (runsQuery.data?.items.length ?? 0) === 0 ? (
          <EmptyState title="还没有运行记录" />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-4 py-3">数据集</th>
                  <th className="px-4 py-3">检索模式</th>
                  <th className="px-4 py-3">检索配置</th>
                  <th className="px-4 py-3">状态</th>
                  <th className="px-4 py-3">进度</th>
                  <th className="px-4 py-3">通过率</th>
                  <th className="px-4 py-3">发起人</th>
                  <th className="px-4 py-3">时间</th>
                </tr>
              </thead>
              <tbody>
                {(runsQuery.data?.items ?? []).map((run) => (
                  <tr
                    key={run.id}
                    className="border-b border-slate-100 last:border-0"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/evaluations/runs/${run.id}`}
                        className="font-medium text-slate-900 hover:underline"
                      >
                        {run.dataset_name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {EVAL_MODE_LABEL[run.retrieval_mode]}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatConfigShort(run.retrieval_config)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {EVAL_RUN_STATUS_LABEL[run.status]}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {run.completed_items}/{run.total_items}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatPercent(run.metrics?.pass_rate)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {run.created_by}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {formatDate(run.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      {isLeader ? (
        <section>
          <h2 className="mb-3 text-lg font-semibold text-slate-900">
            成员权限
          </h2>
          {permissionsQuery.isLoading ? (
            <TableSkeleton rows={3} columns={4} />
          ) : (
            <Card className="p-0">
              <table className="w-full text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">成员</th>
                    <th className="px-4 py-3">用户名</th>
                    <th className="px-4 py-3">角色</th>
                    <th className="px-4 py-3">评测权限</th>
                  </tr>
                </thead>
                <tbody>
                  {(permissionsQuery.data?.items ?? []).map((member) => (
                    <tr
                      key={member.id}
                      className="border-b border-slate-100 last:border-0"
                    >
                      <td className="px-4 py-3">
                        {member.display_name}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {member.username}
                      </td>
                      <td className="px-4 py-3 text-slate-600">
                        {member.role === "leader" ? "领导" : "员工"}
                      </td>
                      <td className="px-4 py-3">
                        <label className="inline-flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={member.can_evaluate}
                            disabled={member.role === "leader"}
                            onChange={(event) =>
                              permissionMutation.mutate({
                                userId: member.id,
                                enabled: event.target.checked,
                              })
                            }
                          />
                          <span className="text-slate-600">
                            {member.can_evaluate
                              ? "可进入评测"
                              : "无权限"}
                          </span>
                        </label>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </section>
      ) : null}

      <Dialog
        open={createOpen}
        title="新建数据集"
        onClose={() => setCreateOpen(false)}
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm text-slate-600">
              名称
            </label>
            <Input
              value={name}
              maxLength={100}
              onChange={(event) => setName(event.target.value)}
              placeholder="例如 RAG 回归集 v1"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm text-slate-600">
              说明
            </label>
            <Textarea
              rows={3}
              value={description}
              maxLength={2000}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <div className="flex justify-end gap-2">
            <ButtonSecondary onClick={() => setCreateOpen(false)}>
              取消
            </ButtonSecondary>
            <Button
              disabled={!name.trim() || createMutation.isPending}
              onClick={() => {
                setError("");
                createMutation.mutate();
              }}
            >
              {createMutation.isPending ? "创建中..." : "创建"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
