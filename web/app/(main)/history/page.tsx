"use client";

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Pagination } from "@/components/pagination";
import {
  ButtonSecondary,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  TableSkeleton,
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  ConversationSummary,
  Paginated,
} from "@/lib/types";
import { formatDate } from "@/lib/utils";

const PAGE_SIZE = 20;

export default function HistoryPage() {
  const { user } = useAuth();
  const router = useRouter();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  const query = useQuery({
    queryKey: ["conversations", "history", page],
    queryFn: () =>
      apiFetch<Paginated<ConversationSummary>>(
        `/conversations?page=${page}&page_size=${PAGE_SIZE}`,
      ),
    enabled: Boolean(user),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/conversations/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["conversations"],
      });
    },
    onError: (err) =>
      setError(err instanceof Error ? err.message : "删除会话失败"),
  });

  const items = query.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title="我的查询历史"
        description="只显示你自己的会话记录。"
      />

      {error ? (
        <div className="mb-4">
          <ErrorState message={error} />
        </div>
      ) : null}

      {query.isLoading ? (
        <TableSkeleton rows={5} columns={3} />
      ) : null}
      {query.isError ? (
        <ErrorState
          message={
            query.error instanceof Error
              ? query.error.message
              : "加载历史失败"
          }
          onRetry={() => void query.refetch()}
        />
      ) : null}

      {!query.isLoading && !query.isError ? (
        items.length === 0 ? (
          <EmptyState
            title="还没有问答记录"
            description="去问答页提一个问题，这里会保存你的会话。"
          />
        ) : (
          <>
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">标题</th>
                    <th className="px-4 py-3">最后更新</th>
                    <th className="px-4 py-3">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((conversation) => (
                    <tr
                      key={conversation.id}
                      className="border-b border-slate-100 last:border-0"
                    >
                      <td className="px-4 py-3 font-medium text-slate-900">
                        {conversation.title}
                      </td>
                      <td className="px-4 py-3">
                        {formatDate(conversation.updated_at)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <ButtonSecondary
                            className="px-2 py-1 text-xs"
                            onClick={() =>
                              router.push(
                                `/chat?conversation_id=${conversation.id}`,
                              )
                            }
                          >
                            打开
                          </ButtonSecondary>
                          <ButtonSecondary
                            className="px-2 py-1 text-xs"
                            onClick={() => {
                              if (
                                window.confirm(
                                  "确定删除这个会话吗？",
                                )
                              ) {
                                deleteMutation.mutate(conversation.id);
                              }
                            }}
                          >
                            删除
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
                total={query.data?.total ?? 0}
                onChange={setPage}
              />
            </div>
          </>
        )
      ) : null}
    </div>
  );
}
