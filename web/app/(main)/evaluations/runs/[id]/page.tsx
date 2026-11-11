"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Fragment, useState } from "react";

import {
  Badge,
  ButtonSecondary,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Select,
  TableSkeleton,
} from "@/components/ui";
import { API_BASE, apiFetch } from "@/lib/api";
import type {
  EvalCompare,
  EvalRun,
  EvalRunItem,
} from "@/lib/types";
import {
  EVAL_ITEM_STATUS_LABEL,
  EVAL_METRIC_LABEL,
  EVAL_MODE_LABEL,
  EVAL_RUN_STATUS_LABEL,
  formatDate,
  formatPercent,
} from "@/lib/utils";

const CONFIG_KEYS = [
  "hybrid_enabled",
  "rerank_enabled",
  "rewrite_enabled",
  "candidate_k",
  "final_k",
  "rerank_threshold",
  "context_token_budget",
];

function formatRetrievalConfig(
  config?: Record<string, unknown> | null,
): string {
  if (!config) return "未记录";
  return CONFIG_KEYS.filter((key) => config[key] !== undefined)
    .map((key) => `${key}=${String(config[key])}`)
    .join(" · ");
}

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

const ITEM_STATUS_STYLE: Record<string, string> = {
  passed: "bg-emerald-50 text-emerald-700",
  failed: "bg-red-50 text-red-700",
  invalid: "bg-amber-50 text-amber-700",
  error: "bg-orange-50 text-orange-700",
  running: "bg-blue-50 text-blue-700",
  pending: "bg-slate-100 text-slate-600",
  cancelled: "bg-slate-100 text-slate-500",
};

function formatMetric(key: string, value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "-";
  }
  if (key.endsWith("_rate") || key === "pass_rate") {
    return formatPercent(value);
  }
  if (key === "avg_latency_ms") {
    return `${Math.round(value)} ms`;
  }
  if (
    key === "invalid_items" ||
    key === "error_items" ||
    key === "passed_items" ||
    key === "valid_items"
  ) {
    return String(value);
  }
  return value.toFixed(3);
}

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params.id;
  const [baselineId, setBaselineId] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [notice, setNotice] = useState("");

  const runQuery = useQuery({
    queryKey: ["eval", "run", runId],
    queryFn: () => apiFetch<EvalRun>(`/eval/runs/${runId}`),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) {
        return false;
      }
      return data.status === "pending" || data.status === "running"
        ? 2000
        : false;
    },
  });

  const run = runQuery.data;
  const active = run?.status === "pending" || run?.status === "running";

  const itemsQuery = useQuery({
    queryKey: ["eval", "run", runId, "items", statusFilter],
    queryFn: () =>
      apiFetch<{ items: EvalRunItem[]; total: number }>(
        `/eval/runs/${runId}/items?page_size=200${
          statusFilter ? `&status=${statusFilter}` : ""
        }`,
      ),
    refetchInterval: active ? 2000 : false,
  });

  const runsQuery = useQuery({
    queryKey: ["eval", "runs", run?.dataset_id],
    queryFn: () =>
      apiFetch<{ items: EvalRun[] }>(
        `/eval/runs?dataset_id=${run?.dataset_id}`,
      ),
    enabled: Boolean(run?.dataset_id),
  });

  const compareQuery = useQuery({
    queryKey: ["eval", "compare", runId, baselineId],
    queryFn: () =>
      apiFetch<EvalCompare>(
        `/eval/runs/${runId}/compare?baseline_id=${baselineId}`,
      ),
    enabled: Boolean(baselineId),
  });

  const cancel = async () => {
    try {
      await apiFetch<EvalRun>(`/eval/runs/${runId}/cancel`, {
        method: "POST",
      });
      setNotice("已请求取消，等待当前轮次结束");
      void runQuery.refetch();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "取消失败");
    }
  };

  if (runQuery.isLoading) {
    return <TableSkeleton rows={5} columns={6} />;
  }
  if (runQuery.error || !run) {
    return (
      <ErrorState
        message={
          runQuery.error instanceof Error
            ? runQuery.error.message
            : "运行不存在"
        }
        onRetry={() => void runQuery.refetch()}
      />
    );
  }

  const metrics = run.metrics ?? {};
  const metricKeys = Object.keys(EVAL_METRIC_LABEL).filter(
    (key) => metrics[key] !== undefined && metrics[key] !== null,
  );
  const baselineOptions = (runsQuery.data?.items ?? []).filter(
    (item) => item.id !== run.id,
  );
  const items = itemsQuery.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title={`${run.dataset_name} · 评测运行`}
        description={`${EVAL_MODE_LABEL[run.retrieval_mode]} · 发起人 ${run.created_by} · ${formatDate(run.created_at)}`}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href={`/evaluations/${run.dataset_id}`}
              className="inline-flex items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              返回数据集
            </Link>
            <a
              href={`${API_BASE}/eval/runs/${run.id}/export?format=jsonl`}
              className="inline-flex items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              导出 JSONL
            </a>
            <a
              href={`${API_BASE}/eval/runs/${run.id}/export?format=csv`}
              className="inline-flex items-center rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              导出 CSV
            </a>
            {active ? (
              <ButtonSecondary onClick={() => void cancel()}>
                取消运行
              </ButtonSecondary>
            ) : null}
          </div>
        }
      />

      {run.retrieval_config ? (
        <div className="mb-4 flex flex-wrap gap-2 text-xs text-slate-600">
          <span className="rounded-md bg-slate-100 px-2 py-1">
            检索配置：{formatRetrievalConfig(run.retrieval_config)}
          </span>
        </div>
      ) : null}

      {notice ? (
        <p className="mb-4 rounded-md bg-slate-100 px-4 py-2 text-sm text-slate-700">
          {notice}
        </p>
      ) : null}

      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-4">
          <Badge className="bg-slate-100 text-slate-700">
            {EVAL_RUN_STATUS_LABEL[run.status]}
          </Badge>
          <div className="min-w-[200px] flex-1">
            <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-2 rounded-full bg-slate-900 transition-all"
                style={{ width: `${Math.round(run.progress * 100)}%` }}
              />
            </div>
          </div>
          <p className="text-sm text-slate-600">
            {run.completed_items}/{run.total_items} 轮次
          </p>
          <p className="text-sm text-slate-500">
            开始 {formatDate(run.started_at)} · 结束{" "}
            {formatDate(run.finished_at)}
          </p>
        </div>
        {run.error ? (
          <p className="mt-3 text-sm text-red-600">{run.error}</p>
        ) : null}
      </Card>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-slate-900">
          汇总指标
        </h2>
        {metricKeys.length === 0 ? (
          <EmptyState title="运行结束后展示指标" />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {metricKeys.map((key) => (
              <Card key={key} className="p-4">
                <p className="text-xs text-slate-500">
                  {EVAL_METRIC_LABEL[key]}
                </p>
                <p className="mt-1 text-xl font-semibold text-slate-900">
                  {formatMetric(key, metrics[key])}
                </p>
              </Card>
            ))}
          </div>
        )}
      </section>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-slate-900">
          基线对比
        </h2>
        <Card>
          <div className="flex flex-wrap items-center gap-3">
            <Select
              className="w-72"
              value={baselineId}
              onChange={(event) => setBaselineId(event.target.value)}
            >
              <option value="">选择同一数据集的历史运行</option>
              {baselineOptions.map((item) => (
                <option key={item.id} value={item.id}>
                  {formatDate(item.created_at)} ·{" "}
                  {EVAL_MODE_LABEL[item.retrieval_mode]} ·{" "}
                  {formatConfigShort(item.retrieval_config)} ·{" "}
                  {EVAL_RUN_STATUS_LABEL[item.status]}
                </option>
              ))}
            </Select>
            {compareQuery.isLoading ? (
              <span className="text-sm text-slate-500">对比中...</span>
            ) : null}
          </div>
          {compareQuery.error ? (
            <p className="mt-3 text-sm text-red-600">
              {compareQuery.error instanceof Error
                ? compareQuery.error.message
                : "对比失败"}
            </p>
          ) : null}
          {compareQuery.data ? (
            <div className="mt-4 space-y-4">
              <div className="flex flex-wrap gap-4 text-xs text-slate-600">
                <span>
                  当前：{formatRetrievalConfig(compareQuery.data.current.retrieval_config)}
                </span>
                <span>
                  基线：{formatRetrievalConfig(compareQuery.data.baseline.retrieval_config)}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-xs uppercase text-slate-500">
                    <tr>
                      <th className="py-2">指标</th>
                      <th className="py-2">当前</th>
                      <th className="py-2">基线</th>
                      <th className="py-2">变化</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(compareQuery.data.metric_delta).map(
                      ([key, delta]) => (
                        <tr
                          key={key}
                          className="border-t border-slate-100"
                        >
                          <td className="py-2 text-slate-600">
                            {EVAL_METRIC_LABEL[key] ?? key}
                          </td>
                          <td className="py-2">
                            {formatMetric(
                              key,
                              compareQuery.data.current.metrics?.[key],
                            )}
                          </td>
                          <td className="py-2 text-slate-500">
                            {formatMetric(
                              key,
                              compareQuery.data.baseline.metrics?.[key],
                            )}
                          </td>
                          <td
                            className={
                              delta > 0
                                ? "py-2 text-emerald-600"
                                : delta < 0
                                  ? "py-2 text-red-600"
                                  : "py-2 text-slate-500"
                            }
                          >
                            {delta > 0 ? "+" : ""}
                            {formatMetric(key, delta)}
                          </td>
                        </tr>
                      ),
                    )}
                  </tbody>
                </table>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <p className="mb-2 text-sm font-medium text-red-600">
                    新增失败（{compareQuery.data.case_changes.newly_failed.length}）
                  </p>
                  <ul className="space-y-1 text-sm text-slate-600">
                    {compareQuery.data.case_changes.newly_failed.map(
                      (item) => (
                        <li key={`${item.case_id}-${item.turn_index}`}>
                          {item.case_title} · 第 {item.turn_index} 轮
                        </li>
                      ),
                    )}
                  </ul>
                </div>
                <div>
                  <p className="mb-2 text-sm font-medium text-emerald-600">
                    新修复（{compareQuery.data.case_changes.newly_passed.length}）
                  </p>
                  <ul className="space-y-1 text-sm text-slate-600">
                    {compareQuery.data.case_changes.newly_passed.map(
                      (item) => (
                        <li key={`${item.case_id}-${item.turn_index}`}>
                          {item.case_title} · 第 {item.turn_index} 轮
                        </li>
                      ),
                    )}
                  </ul>
                </div>
              </div>
            </div>
          ) : null}
        </Card>
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">逐轮结果</h2>
          <Select
            className="w-40"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">全部状态</option>
            <option value="passed">通过</option>
            <option value="failed">未通过</option>
            <option value="invalid">失效</option>
            <option value="error">出错</option>
            <option value="cancelled">已取消</option>
          </Select>
        </div>
        {itemsQuery.isLoading ? (
          <TableSkeleton rows={5} columns={7} />
        ) : items.length === 0 ? (
          <EmptyState title="没有结果" />
        ) : (
          <Card className="overflow-x-auto p-0">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase text-slate-500">
                <tr>
                  <th className="px-3 py-3">用例</th>
                  <th className="px-3 py-3">轮次</th>
                  <th className="px-3 py-3">状态</th>
                  <th className="px-3 py-3">检索命中</th>
                  <th className="px-3 py-3">引用精确率</th>
                  <th className="px-3 py-3">评分</th>
                  <th className="px-3 py-3">拒答</th>
                  <th className="px-3 py-3">耗时</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <Fragment key={item.id}>
                    <tr
                      className="cursor-pointer border-b border-slate-100 hover:bg-slate-50"
                      onClick={() =>
                        setExpanded(
                          expanded === item.id ? null : item.id,
                        )
                      }
                    >
                      <td className="px-3 py-2">{item.case_title}</td>
                      <td className="px-3 py-2 text-slate-600">
                        {item.turn_index}
                      </td>
                      <td className="px-3 py-2">
                        <Badge
                          className={
                            ITEM_STATUS_STYLE[item.status] ??
                            "bg-slate-100 text-slate-600"
                          }
                        >
                          {EVAL_ITEM_STATUS_LABEL[item.status]}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {item.retrieval_hit === null
                          ? "-"
                          : item.retrieval_hit
                            ? "是"
                            : "否"}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {item.citation_precision === null
                          ? "-"
                          : item.citation_precision.toFixed(2)}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {item.judge_score ?? "-"}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {item.refused === null
                          ? "-"
                          : item.refused
                            ? "是"
                            : "否"}
                      </td>
                      <td className="px-3 py-2 text-slate-600">
                        {item.latency_ms ?? "-"}
                      </td>
                    </tr>
                    {expanded === item.id ? (
                      <tr>
                        <td
                          colSpan={8}
                          className="border-b border-slate-100 bg-slate-50 px-4 py-3 text-sm"
                        >
                          <div className="space-y-2">
                            <p>
                              <span className="text-slate-500">问题：</span>
                              {item.question}
                            </p>
                            {item.retrieval_query &&
                            item.retrieval_query !== item.question ? (
                              <p>
                                <span className="text-slate-500">
                                  检索问题：
                                </span>
                                {item.retrieval_query}
                              </p>
                            ) : null}
                            {item.reference_answer ? (
                              <p>
                                <span className="text-slate-500">
                                  参考答案：
                                </span>
                                {item.reference_answer}
                              </p>
                            ) : null}
                            <p>
                              <span className="text-slate-500">
                                模型回答：
                              </span>
                              {item.answer || "-"}
                            </p>
                            {item.judge_reason ? (
                              <p>
                                <span className="text-slate-500">
                                  评分理由：
                                </span>
                                {item.judge_reason}
                              </p>
                            ) : null}
                            {item.invalid_reason ? (
                              <p className="text-amber-700">
                                失效原因：{item.invalid_reason}
                              </p>
                            ) : null}
                            {item.error ? (
                              <p className="text-red-600">
                                错误：{item.error}
                              </p>
                            ) : null}
                            {item.retrieved && item.retrieved.length > 0 ? (
                              <div>
                                <p className="text-slate-500">
                                  检索片段：
                                </p>
                                <ul className="mt-1 space-y-1">
                                  {item.retrieved.map((entry) => (
                                    <li
                                      key={`${entry.document_id}-${entry.chunk_index}`}
                                      className="rounded bg-white px-2 py-1"
                                    >
                                      《{entry.document_title}》#
                                      {entry.chunk_index}：
                                      {entry.snippet.slice(0, 120)}
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>
    </div>
  );
}
