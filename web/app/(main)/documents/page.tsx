"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";

import { Pagination } from "@/components/pagination";
import { IndexStatusBadge } from "@/components/status-badge";
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
import { apiFetch, apiUpload } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  BatchDeleteResult,
  DocumentActionResult,
  DocumentItem,
  DownloadResult,
  Paginated,
} from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

export default function DocumentsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const [uploadOpen, setUploadOpen] = useState(false);
  const [editing, setEditing] = useState<DocumentItem | null>(null);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [batchResult, setBatchResult] = useState<BatchDeleteResult | null>(
    null,
  );

  useEffect(() => {
    setSelected(new Set());
    setBatchResult(null);
  }, [search, page]);

  const isLeader = user?.role === "leader";

  const documentsQuery = useQuery({
    queryKey: ["documents", search, page],
    queryFn: () =>
      apiFetch<Paginated<DocumentItem>>(
        `/documents?keyword=${encodeURIComponent(search)}&page=${page}&page_size=${PAGE_SIZE}`,
      ),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) {
        return false;
      }
      const hasActive = data.items.some(
        (item) =>
          item.index_status === "pending" ||
          item.index_status === "indexing",
      );
      return hasActive ? 3000 : false;
    },
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["documents"] });
  };

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!file) {
        throw new Error("请选择文件");
      }
      if (!title.trim()) {
        throw new Error("请填写文档标题");
      }
      const form = new FormData();
      form.append("title", title.trim());
      form.append("file", file);
      return apiUpload<DocumentActionResult>("/documents", form);
    },
    onSuccess: (result) => {
      setUploadOpen(false);
      setTitle("");
      setFile(null);
      setNotice(
        result.mode === "direct"
          ? "上传成功，正在解析索引"
          : "已提交审批，等待领导处理",
      );
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "上传失败"),
  });

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editing) {
        throw new Error("没有选中文档");
      }
      const form = new FormData();
      if (title.trim()) {
        form.append("title", title.trim());
      }
      if (file) {
        form.append("file", file);
      }
      return apiUpload<DocumentActionResult>(
        `/documents/${editing.id}`,
        form,
        "PUT",
      );
    },
    onSuccess: (result) => {
      setEditing(null);
      setTitle("");
      setFile(null);
      setNotice(
        result.mode === "direct" ? "文档已更新" : "修改已提交审批",
      );
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "更新失败"),
  });

  const deleteMutation = useMutation({
    mutationFn: (document: DocumentItem) =>
      apiFetch<DocumentActionResult>(`/documents/${document.id}`, {
        method: "DELETE",
      }),
    onSuccess: (result) => {
      setNotice(
        result.mode === "direct" ? "文档已删除" : "删除已提交审批",
      );
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "删除失败"),
  });

  const batchDeleteMutation = useMutation({
    mutationFn: (ids: string[]) =>
      apiFetch<BatchDeleteResult>("/documents/batch-delete", {
        method: "POST",
        body: JSON.stringify({ ids }),
      }),
    onSuccess: (result) => {
      setBatchResult(result);
      setSelected(new Set());
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "批量删除失败"),
  });

  const reindexMutation = useMutation({
    mutationFn: (document: DocumentItem) =>
      apiFetch<DocumentActionResult>(
        `/documents/${document.id}/reindex`,
        { method: "POST" },
      ),
    onSuccess: () => {
      setNotice("已重新提交索引");
      refresh();
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "重新索引失败"),
  });

  async function download(document: DocumentItem) {
    try {
      const result = await apiFetch<DownloadResult>(
        `/documents/${document.id}/download`,
      );
      window.open(result.download_url, "_blank");
    } catch (err) {
      setError(err instanceof Error ? err.message : "下载失败");
    }
  }

  function openUpload() {
    setError("");
    setNotice("");
    setTitle("");
    setFile(null);
    setUploadOpen(true);
  }

  function openEdit(document: DocumentItem) {
    setError("");
    setNotice("");
    setEditing(document);
    setTitle(document.title);
    setFile(null);
  }

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setError("");
    setPage(1);
    setSearch(keyword.trim());
  }

  const items = documentsQuery.data?.items ?? [];
  const allSelected =
    items.length > 0 && items.every((item) => selected.has(item.id));

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

  return (
    <div>
      <PageHeader
        title="文档"
        description="上传、搜索、下载企业文档；员工变更需领导审批。"
        action={
          <div className="flex items-center gap-2">
            {selected.size > 0 ? (
              <ButtonSecondary
                className="border-red-200 text-red-600"
                disabled={batchDeleteMutation.isPending}
                onClick={() => {
                  setError("");
                  setNotice("");
                  batchDeleteMutation.mutate(Array.from(selected));
                }}
              >
                {batchDeleteMutation.isPending
                  ? "删除中..."
                  : `批量删除（${selected.size}）`}
              </ButtonSecondary>
            ) : null}
            <Button onClick={openUpload}>上传文档</Button>
          </div>
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

      {batchResult ? (
        <div className="mb-4 rounded-md border border-green-200 bg-green-50 p-3 text-sm text-green-800">
          <div className="flex flex-wrap items-center gap-3">
            <span>
              {batchResult.mode === "direct"
                ? `已移入回收站 ${batchResult.deleted.length} 篇`
                : `已提交删除申请 ${batchResult.submitted.length} 条`}
              {batchResult.skipped.length > 0
                ? `，跳过 ${batchResult.skipped.length} 篇`
                : ""}
            </span>
            {isLeader && batchResult.deleted.length > 0 ? (
              <Link
                href="/documents/trash"
                className="underline"
              >
                去回收站
              </Link>
            ) : null}
            <button
              className="ml-auto text-green-700 hover:underline"
              onClick={() => setBatchResult(null)}
            >
              关闭
            </button>
          </div>
          {batchResult.skipped.length > 0 ? (
            <ul className="mt-2 space-y-1 text-xs text-green-700">
              {batchResult.skipped.slice(0, 5).map((item) => (
                <li key={item.id}>
                  {item.title ?? item.id}：{item.reason}
                </li>
              ))}
              {batchResult.skipped.length > 5 ? (
                <li>等 {batchResult.skipped.length} 篇</li>
              ) : null}
            </ul>
          ) : null}
        </div>
      ) : null}

      <Card className="mb-4">
        <form className="flex flex-col gap-2 sm:flex-row" onSubmit={submitSearch}>
          <Input
            placeholder="搜索标题或文件名"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <ButtonSecondary type="submit">搜索</ButtonSecondary>
        </form>
      </Card>

      {documentsQuery.isLoading ? (
        <TableSkeleton rows={5} columns={6} />
      ) : null}
      {documentsQuery.isError ? (
        <ErrorState
          message={
            documentsQuery.error instanceof Error
              ? documentsQuery.error.message
              : "加载文档失败"
          }
          onRetry={() => void documentsQuery.refetch()}
        />
      ) : null}

      {!documentsQuery.isLoading && !documentsQuery.isError ? (
        items.length === 0 ? (
          <EmptyState
            title="还没有文档"
            description="领导上传后直接生效；员工上传需要领导审批。"
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
                        name="select-all-documents"
                      />
                    </th>
                    <th className="px-4 py-3">标题</th>
                    <th className="px-4 py-3">大小</th>
                    <th className="px-4 py-3">索引状态</th>
                    <th className="px-4 py-3">上传人</th>
                    <th className="px-4 py-3">更新时间</th>
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
                        <IndexStatusBadge status={document.index_status} />
                      </td>
                      <td className="px-4 py-3">
                        {document.uploaded_by.display_name}
                      </td>
                      <td className="px-4 py-3">
                        {formatDate(document.updated_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-2">
                          <ButtonSecondary
                            className="px-2 py-1 text-xs"
                            onClick={() => void download(document)}
                          >
                            下载
                          </ButtonSecondary>
                          <ButtonSecondary
                            className="px-2 py-1 text-xs"
                            onClick={() => openEdit(document)}
                          >
                            编辑
                          </ButtonSecondary>
                          <ButtonSecondary
                            className="px-2 py-1 text-xs"
                            onClick={() => {
                              if (
                                window.confirm(
                                  `确定将《${document.title}》移入回收站吗？`,
                                )
                              ) {
                                deleteMutation.mutate(document);
                              }
                            }}
                          >
                            删除
                          </ButtonSecondary>
                          {isLeader &&
                          document.index_status === "failed" ? (
                            <ButtonSecondary
                              className="px-2 py-1 text-xs"
                              onClick={() =>
                                reindexMutation.mutate(document)
                              }
                            >
                              重新索引
                            </ButtonSecondary>
                          ) : null}
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
                total={documentsQuery.data?.total ?? 0}
                onChange={setPage}
              />
            </div>
          </>
        )
      ) : null}

      <Dialog
        open={uploadOpen}
        title="上传文档"
        onClose={() => setUploadOpen(false)}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            uploadMutation.mutate();
          }}
        >
          <Input
            placeholder="文档标题"
            maxLength={255}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <Input
            type="file"
            accept=".pdf,.docx,.md,.markdown,.txt"
            onChange={(event) =>
              setFile(event.target.files?.[0] ?? null)
            }
          />
          <p className="text-xs text-slate-500">
            支持 PDF / DOCX / Markdown / TXT，单文件不超过 50MB。
            {isLeader ? " 领导上传直接生效。" : " 员工上传需领导审批。"}
          </p>
          <div className="flex justify-end gap-2">
            <ButtonSecondary
              type="button"
              onClick={() => setUploadOpen(false)}
            >
              取消
            </ButtonSecondary>
            <Button disabled={uploadMutation.isPending}>
              {uploadMutation.isPending ? "提交中..." : "提交"}
            </Button>
          </div>
        </form>
      </Dialog>

      <Dialog
        open={Boolean(editing)}
        title="编辑文档"
        onClose={() => setEditing(null)}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            updateMutation.mutate();
          }}
        >
          <Input
            placeholder="文档标题"
            maxLength={255}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
          <Input
            type="file"
            accept=".pdf,.docx,.md,.markdown,.txt"
            onChange={(event) =>
              setFile(event.target.files?.[0] ?? null)
            }
          />
          <p className="text-xs text-slate-500">
            不选新文件则只修改标题。
            {isLeader ? " 领导修改直接生效。" : " 员工修改需领导审批。"}
          </p>
          <div className="flex justify-end gap-2">
            <ButtonSecondary
              type="button"
              onClick={() => setEditing(null)}
            >
              取消
            </ButtonSecondary>
            <Button disabled={updateMutation.isPending}>
              {updateMutation.isPending ? "提交中..." : "提交"}
            </Button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
