"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { Pagination } from "@/components/pagination";
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
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import type { BatchResult, Paginated, TrashDocument } from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;
const PURGE_CONFIRM_TEXT = "彻底删除";

export default function TrashPage() {
  const queryClient = useQueryClient();
  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [purgeText, setPurgeText] = useState("");
  const [purgeIds, setPurgeIds] = useState<string[]>([]);

  const trashQuery = useQuery({
    queryKey: ["documents", "trash", search, page],
    queryFn: () =>
      apiFetch<Paginated<TrashDocument>>(
        `/documents/trash?keyword=${encodeURIComponent(search)}&page=${page}&page_size=${PAGE_SIZE}`,
      ),
  });

  const items = trashQuery.data?.items ?? [];
  const allSelected =
    items.length > 0 && items.every((item) => selected.has(item.id));

  const refresh = () => {
    setSelected(new Set());
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const toggleAll = () => {
    setSelected(
      allSelected ? new Set() : new Set(items.map((item) => item.id)),
    );
  };

  const toggleOne = (documentId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(documentId)) {
        next.delete(documentId);
      } else {
        next.add(documentId);
      }
      return next;
    });
  };

  const restoreMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiFetch<BatchResult>("/documents/trash/restore", {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    onSuccess: (result) => {
      setNotice(
        `已恢复 ${result.processed.length} 篇` +
          (result.skipped.length > 0
            ? `，跳过 ${result.skipped.length} 篇：${result.skipped
                .map((item) => item.reason)
                .join("；")}`
            : ""),
      );
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "恢复失败"),
  });

  const purgeMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiFetch<BatchResult>("/documents/trash/purge", {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    onSuccess: (result) => {
      setPurgeOpen(false);
      setPurgeText("");
      setPurgeIds([]);
      setNotice(
        `已彻底删除 ${result.processed.length} 篇` +
          (result.skipped.length > 0
            ? `，跳过 ${result.skipped.length} 篇`
            : ""),
      );
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "彻底删除失败"),
  });

  return (
    <div>
      <PageHeader
        title="回收站"
        description="已删除文档可恢复；彻底删除后分块与文件将被清理。"
        action={
          <div className="flex items-center gap-2">
            {selected.size > 0 ? (
              <>
                <ButtonSecondary
                  disabled={restoreMutation.isPending}
                  onClick={() =>
                    restoreMutation.mutate(Array.from(selected))
                  }
                >
                  恢复（{selected.size}）
                </ButtonSecondary>
                <ButtonSecondary
                  className="border-red-200 text-red-600"
                  onClick={() => {
                    setPurgeIds(Array.from(selected));
                    setPurgeText("");
                    setPurgeOpen(true);
                  }}
                >
                  彻底删除（{selected.size}）
                </ButtonSecondary>
              </>
            ) : null}
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

      <Card className="mb-4">
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            setSearch(keyword.trim());
          }}
        >
          <Input
            placeholder="搜索标题或文件名"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <ButtonSecondary type="submit">搜索</ButtonSecondary>
        </form>
      </Card>

      {trashQuery.isLoading ? <TableSkeleton rows={5} columns={6} /> : null}
      {trashQuery.isError ? (
        <ErrorState
          message={
            trashQuery.error instanceof Error
              ? trashQuery.error.message
              : "加载回收站失败"
          }
          onRetry={() => void trashQuery.refetch()}
        />
      ) : null}

      {!trashQuery.isLoading && !trashQuery.isError ? (
        items.length === 0 ? (
          <EmptyState
            title="回收站是空的"
            description="删除的文档会出现在这里，可恢复或彻底删除。"
          />
        ) : (
          <>
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[860px] text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleAll}
                        aria-label="全选当前页"
                        name="select-all-trash"
                      />
                    </th>
                    <th className="px-4 py-3">标题</th>
                    <th className="px-4 py-3">大小</th>
                    <th className="px-4 py-3">上传人</th>
                    <th className="px-4 py-3">删除时间</th>
                    <th className="px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((document) => (
                    <tr
                      key={document.id}
                      className="border-b border-slate-100 last:border-0"
                    >
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selected.has(document.id)}
                          onChange={() => toggleOne(document.id)}
                          aria-label={`选择 ${document.title}`}
                          name={`select-${document.id}`}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-900">
                          {document.title}
                        </div>
                        <div className="text-xs text-slate-500">
                          {document.filename}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {formatBytes(document.size_bytes)}
                      </td>
                      <td className="px-4 py-3">
                        {document.uploaded_by.display_name}
                      </td>
                      <td className="px-4 py-3">
                        {formatDate(document.deleted_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          <ButtonSecondary
                            className="px-2 py-1 text-xs"
                            disabled={restoreMutation.isPending}
                            onClick={() =>
                              restoreMutation.mutate([document.id])
                            }
                          >
                            恢复
                          </ButtonSecondary>
                          <ButtonSecondary
                            className="px-2 py-1 text-xs text-red-600"
                            onClick={() => {
                              setPurgeIds([document.id]);
                              setPurgeText("");
                              setPurgeOpen(true);
                            }}
                          >
                            彻底删除
                          </ButtonSecondary>
                        </div>
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
                total={trashQuery.data?.total ?? 0}
                onChange={setPage}
              />
            </div>
          </>
        )
      ) : null}

      <Dialog
        open={purgeOpen}
        title="彻底删除文档"
        onClose={() => setPurgeOpen(false)}
      >
        <div className="space-y-4">
          <p className="text-sm text-slate-600">
            将彻底删除 {purgeIds.length} 篇文档，分块与文件会被清理，
            此操作不可恢复。请输入「{PURGE_CONFIRM_TEXT}」确认。
          </p>
          <Input
            value={purgeText}
            onChange={(event) => setPurgeText(event.target.value)}
            placeholder={PURGE_CONFIRM_TEXT}
            name="purge_confirm"
          />
          {error ? <ErrorState message={error} /> : null}
          <div className="flex justify-end gap-2">
            <ButtonSecondary onClick={() => setPurgeOpen(false)}>
              取消
            </ButtonSecondary>
            <Button
              disabled={
                purgeText.trim() !== PURGE_CONFIRM_TEXT ||
                purgeMutation.isPending
              }
              onClick={() => purgeMutation.mutate(purgeIds)}
            >
              {purgeMutation.isPending ? "删除中..." : "确认彻底删除"}
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
}
