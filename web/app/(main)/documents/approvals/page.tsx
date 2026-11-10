"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { Pagination } from "@/components/pagination";
import {
  DocumentActionBadge,
  DocumentChangeStatusBadge,
} from "@/components/status-badge";
import {
  Button,
  ButtonSecondary,
  Card,
  Dialog,
  EmptyState,
  ErrorState,
  PageHeader,
  TableSkeleton,
  Textarea,
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  BatchResult,
  DocumentActionResult,
  DocumentChange,
  DocumentChangeStatus,
  Paginated,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;
const TABS: { key: DocumentChangeStatus; label: string }[] = [
  { key: "pending", label: "待审批" },
  { key: "approved", label: "已通过" },
  { key: "rejected", label: "已驳回" },
];

export default function DocumentApprovalsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isLeader = user?.role === "leader";

  const [tab, setTab] = useState<DocumentChangeStatus>("pending");
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [reviewing, setReviewing] = useState<DocumentChange | null>(null);
  const [decision, setDecision] = useState<"approve" | "reject">(
    "approve",
  );
  const [comment, setComment] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchDecision, setBatchDecision] = useState<
    "approve" | "reject" | null
  >(null);
  const [batchComment, setBatchComment] = useState("");

  useEffect(() => {
    setSelected(new Set());
  }, [tab, page]);

  const changesQuery = useQuery({
    queryKey: ["document-changes", tab, page],
    queryFn: () =>
      apiFetch<Paginated<DocumentChange>>(
        `/document-changes?status=${tab}&page=${page}&page_size=${PAGE_SIZE}`,
      ),
    enabled: isLeader,
  });

  const reviewMutation = useMutation({
    mutationFn: async () => {
      if (!reviewing) {
        throw new Error("没有选中的变更");
      }
      if (decision === "reject" && !comment.trim()) {
        throw new Error("驳回必须填写原因");
      }
      return apiFetch<DocumentActionResult>(
        `/document-changes/${reviewing.id}/${decision}`,
        {
          method: "POST",
          body: JSON.stringify({
            comment: comment.trim() || undefined,
          }),
        },
      );
    },
    onSuccess: () => {
      setNotice(decision === "approve" ? "已通过变更" : "已驳回变更");
      setReviewing(null);
      setComment("");
      void queryClient.invalidateQueries({
        queryKey: ["document-changes"],
      });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "审批失败"),
  });

  const batchMutation = useMutation({
    mutationFn: async () => {
      if (!batchDecision) {
        throw new Error("没有选择操作");
      }
      if (batchDecision === "reject" && !batchComment.trim()) {
        throw new Error("驳回必须填写原因");
      }
      return apiFetch<BatchResult>(
        `/document-changes/batch-${batchDecision}`,
        {
          method: "POST",
          body: JSON.stringify({
            ids: Array.from(selected),
            comment: batchComment.trim() || undefined,
          }),
        },
      );
    },
    onSuccess: (result) => {
      setNotice(
        `已处理 ${result.processed.length} 条` +
          (result.skipped.length > 0
            ? `，跳过 ${result.skipped.length} 条：${result.skipped
                .map((item) => item.reason)
                .join("；")}`
            : ""),
      );
      setBatchDecision(null);
      setBatchComment("");
      setSelected(new Set());
      void queryClient.invalidateQueries({
        queryKey: ["document-changes"],
      });
      void queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "批量审批失败"),
  });

  function openReview(
    change: DocumentChange,
    nextDecision: "approve" | "reject",
  ) {
    setError("");
    setNotice("");
    setReviewing(change);
    setDecision(nextDecision);
    setComment("");
  }

  if (!user) {
    return null;
  }
  if (!isLeader) {
    return (
      <ErrorState message="只有领导可以访问文档审批页面" />
    );
  }

  const items = changesQuery.data?.items ?? [];
  const pendingItems = items.filter((item) => item.status === "pending");
  const allSelected =
    pendingItems.length > 0 &&
    pendingItems.every((item) => selected.has(item.id));

  const toggleAll = () => {
    setSelected(
      allSelected
        ? new Set()
        : new Set(pendingItems.map((item) => item.id)),
    );
  };

  const toggleOne = (changeId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(changeId)) {
        next.delete(changeId);
      } else {
        next.add(changeId);
      }
      return next;
    });
  };

  return (
    <div>
      <PageHeader
        title="文档审批"
        description="审批员工提交的文档新增、修改和删除。"
        action={
          selected.size > 0 ? (
            <div className="flex items-center gap-2">
              <ButtonSecondary
                onClick={() => {
                  setBatchComment("");
                  setBatchDecision("approve");
                }}
              >
                批量通过（{selected.size}）
              </ButtonSecondary>
              <ButtonSecondary
                className="border-red-200 text-red-600"
                onClick={() => {
                  setBatchComment("");
                  setBatchDecision("reject");
                }}
              >
                批量驳回（{selected.size}）
              </ButtonSecondary>
            </div>
          ) : null
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

      <div className="mb-4 flex gap-2">
        {TABS.map((item) => (
          <button
            key={item.key}
            className={
              tab === item.key
                ? "rounded-md bg-slate-900 px-3 py-2 text-sm text-white"
                : "rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
            }
            onClick={() => {
              setTab(item.key);
              setPage(1);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      {changesQuery.isLoading ? (
        <TableSkeleton rows={5} columns={6} />
      ) : null}
      {changesQuery.isError ? (
        <ErrorState
          message={
            changesQuery.error instanceof Error
              ? changesQuery.error.message
              : "加载变更失败"
          }
          onRetry={() => void changesQuery.refetch()}
        />
      ) : null}

      {!changesQuery.isLoading && !changesQuery.isError ? (
        items.length === 0 ? (
          <EmptyState
            title="暂无变更"
            description="员工提交文档变更后会出现在这里。"
          />
        ) : (
          <>
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[820px] text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleAll}
                        aria-label="全选当前页"
                        name="select-all-changes"
                      />
                    </th>
                    <th className="px-4 py-3">动作</th>
                    <th className="px-4 py-3">文档</th>
                    <th className="px-4 py-3">申请人</th>
                    <th className="px-4 py-3">提交时间</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((change) => (
                    <tr
                      key={change.id}
                      className="border-b border-slate-100 last:border-0"
                    >
                      <td className="px-4 py-3">
                        {change.status === "pending" ? (
                          <input
                            type="checkbox"
                            checked={selected.has(change.id)}
                            onChange={() => toggleOne(change.id)}
                            aria-label={`选择变更 ${change.document_title ?? change.id}`}
                            name={`select-change-${change.id}`}
                          />
                        ) : null}
                      </td>
                      <td className="px-4 py-3">
                        <DocumentActionBadge action={change.action} />
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">
                          {change.document_title ??
                            change.title ??
                            "-"}
                        </div>
                        <div className="text-xs text-slate-500">
                          {change.filename ?? ""}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {change.requested_by.display_name}
                      </td>
                      <td className="px-4 py-3">
                        {formatDate(change.created_at)}
                      </td>
                      <td className="px-4 py-3">
                        <DocumentChangeStatusBadge
                          status={change.status}
                        />
                      </td>
                      <td className="px-4 py-3">
                        {change.status === "pending" ? (
                          <div className="flex gap-2">
                            <ButtonSecondary
                              className="px-2 py-1 text-xs"
                              onClick={() =>
                                openReview(change, "approve")
                              }
                            >
                              通过
                            </ButtonSecondary>
                            <ButtonSecondary
                              className="px-2 py-1 text-xs"
                              onClick={() =>
                                openReview(change, "reject")
                              }
                            >
                              驳回
                            </ButtonSecondary>
                          </div>
                        ) : (
                          <span className="text-xs text-slate-500">
                            {change.reviewed_by
                              ? `审批人：${change.reviewed_by.display_name}`
                              : "-"}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
            <div className="mt-4">
              <Pagination
                page={page}
                pageSize={PAGE_SIZE}
                total={changesQuery.data?.total ?? 0}
                onChange={setPage}
              />
            </div>
          </>
        )
      ) : null}

      <Dialog
        open={Boolean(reviewing)}
        title={decision === "approve" ? "通过变更" : "驳回变更"}
        onClose={() => setReviewing(null)}
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            {reviewing?.document_title ?? reviewing?.title ?? "-"}
          </p>
          <Textarea
            rows={4}
            name="review_comment"
            placeholder={
              decision === "reject"
                ? "驳回原因（必填）"
                : "审批意见（可选）"
            }
            value={comment}
            onChange={(event) => setComment(event.target.value)}
          />
          <div className="flex justify-end gap-2">
            <ButtonSecondary
              type="button"
              onClick={() => setReviewing(null)}
            >
              取消
            </ButtonSecondary>
            <Button
              disabled={
                reviewMutation.isPending ||
                (decision === "reject" && !comment.trim())
              }
              onClick={() => reviewMutation.mutate()}
            >
              {reviewMutation.isPending ? "提交中..." : "确认"}
            </Button>
          </div>
        </div>
      </Dialog>

      <Dialog
        open={Boolean(batchDecision)}
        title={batchDecision === "reject" ? "批量驳回" : "批量通过"}
        onClose={() => setBatchDecision(null)}
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            将处理 {selected.size} 条待审批变更。
          </p>
          <Textarea
            rows={4}
            name="batch_comment"
            placeholder={
              batchDecision === "reject"
                ? "驳回原因（必填）"
                : "审批意见（可选）"
            }
            value={batchComment}
            onChange={(event) => setBatchComment(event.target.value)}
          />
          {error ? <ErrorState message={error} /> : null}
          <div className="flex justify-end gap-2">
            <ButtonSecondary onClick={() => setBatchDecision(null)}>
              取消
            </ButtonSecondary>
            <Button
              disabled={
                batchMutation.isPending ||
                (batchDecision === "reject" && !batchComment.trim())
              }
              onClick={() => batchMutation.mutate()}
            >
              {batchMutation.isPending ? "提交中..." : "确认"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
