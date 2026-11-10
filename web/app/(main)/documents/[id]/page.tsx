"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";

import { IndexStatusBadge } from "@/components/status-badge";
import {
  ButtonSecondary,
  Card,
  ErrorState,
  PageHeader,
  Spinner,
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import type { DocumentItem, DownloadResult } from "@/lib/types";
import { formatBytes, formatDate } from "@/lib/utils";

export default function DocumentDetailPage() {
  const params = useParams<{ id: string }>();
  const documentId = params.id;
  const router = useRouter();

  const documentQuery = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => apiFetch<DocumentItem>(`/documents/${documentId}`),
    enabled: Boolean(documentId),
  });

  async function download() {
    const result = await apiFetch<DownloadResult>(
      `/documents/${documentId}/download`,
    );
    window.open(result.download_url, "_blank");
  }

  const document = documentQuery.data;

  return (
    <div>
      <PageHeader
        title={document?.title ?? "文档详情"}
        description={document?.filename}
        action={
          <ButtonSecondary onClick={() => router.push("/documents")}>
            返回列表
          </ButtonSecondary>
        }
      />

      {documentQuery.isLoading ? <Spinner label="加载文档" /> : null}
      {documentQuery.isError ? (
        <ErrorState
          message={
            documentQuery.error instanceof Error
              ? documentQuery.error.message
              : "加载文档失败"
          }
          onRetry={() => void documentQuery.refetch()}
        />
      ) : null}

      {document ? (
        <Card>
          <dl className="grid gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs text-slate-500">标题</dt>
              <dd className="mt-1 text-sm text-slate-900">
                {document.title}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">文件名</dt>
              <dd className="mt-1 text-sm text-slate-900">
                {document.filename}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">大小</dt>
              <dd className="mt-1 text-sm text-slate-900">
                {formatBytes(document.size_bytes)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">索引状态</dt>
              <dd className="mt-1">
                <IndexStatusBadge status={document.index_status} />
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">上传人</dt>
              <dd className="mt-1 text-sm text-slate-900">
                {document.uploaded_by.display_name}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">更新时间</dt>
              <dd className="mt-1 text-sm text-slate-900">
                {formatDate(document.updated_at)}
              </dd>
            </div>
          </dl>
          <div className="mt-6 flex gap-2">
            <ButtonSecondary onClick={() => void download()}>
              下载
            </ButtonSecondary>
          </div>
          <p className="mt-4 text-xs text-slate-500">
            编辑、删除和重新索引请在文档列表操作。
          </p>
        </Card>
      ) : null}
    </div>
  );
}
