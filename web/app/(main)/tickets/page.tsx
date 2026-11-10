"use client";

import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Pagination } from "@/components/pagination";
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
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  Select,
  TableSkeleton,
} from "@/components/ui";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { TicketListResponse, UserBrief } from "@/lib/types";
import {
  TICKET_PRIORITY_LABEL,
  TICKET_STATUS_LABEL,
  TICKET_TYPE_LABEL,
  formatDate,
} from "@/lib/utils";

const PAGE_SIZE = 20;

export default function TicketsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const isLeader = user?.role === "leader";

  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [type, setType] = useState("");
  const [priority, setPriority] = useState("");
  const [assigneeId, setAssigneeId] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const employeesQuery = useQuery({
    queryKey: ["users", "employees"],
    queryFn: () =>
      apiFetch<{ items: UserBrief[] }>("/users?role=employee"),
    enabled: Boolean(isLeader),
  });

  const params = new URLSearchParams();
  if (search) params.set("keyword", search);
  if (status) params.set("status", status);
  if (type) params.set("type", type);
  if (priority) params.set("priority", priority);
  if (assigneeId) params.set("assignee_id", assigneeId);
  if (dateFrom) {
    params.set(
      "date_from",
      new Date(`${dateFrom}T00:00:00`).toISOString(),
    );
  }
  if (dateTo) {
    params.set(
      "date_to",
      new Date(`${dateTo}T23:59:59.999`).toISOString(),
    );
  }
  params.set("page", String(page));
  params.set("page_size", String(PAGE_SIZE));
  const queryString = params.toString();

  const ticketsQuery = useQuery({
    queryKey: ["tickets", queryString],
    queryFn: () =>
      apiFetch<TicketListResponse>(`/tickets?${queryString}`),
    enabled: Boolean(user),
  });

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setSearch(keyword.trim());
  }

  function resetFilters() {
    setKeyword("");
    setSearch("");
    setStatus("");
    setType("");
    setPriority("");
    setAssigneeId("");
    setDateFrom("");
    setDateTo("");
    setPage(1);
  }

  const items = ticketsQuery.data?.items ?? [];
  const employees = employeesQuery.data?.items ?? [];

  return (
    <div>
      <PageHeader
        title="工单"
        description={
          isLeader
            ? "查看全部工单并完成审核、指派。"
            : "查看自己提交和被指派的工单。"
        }
        action={
          <Button onClick={() => router.push("/tickets/new")}>
            新建工单
          </Button>
        }
      />

      <Card className="mb-4">
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={submitSearch}
        >
          <Input
            placeholder="搜索工单编号、标题或描述"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <ButtonSecondary type="submit">搜索</ButtonSecondary>
        </form>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          <Select
            value={status}
            onChange={(event) => {
              setStatus(event.target.value);
              setPage(1);
            }}
          >
            <option value="">全部状态</option>
            {Object.entries(TICKET_STATUS_LABEL).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </Select>
          <Select
            value={type}
            onChange={(event) => {
              setType(event.target.value);
              setPage(1);
            }}
          >
            <option value="">全部类型</option>
            {Object.entries(TICKET_TYPE_LABEL).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </Select>
          <Select
            value={priority}
            onChange={(event) => {
              setPriority(event.target.value);
              setPage(1);
            }}
          >
            <option value="">全部优先级</option>
            {Object.entries(TICKET_PRIORITY_LABEL).map(
              ([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ),
            )}
          </Select>
          {isLeader ? (
            <Select
              value={assigneeId}
              onChange={(event) => {
                setAssigneeId(event.target.value);
                setPage(1);
              }}
            >
              <option value="">全部处理人</option>
              {employees.map((employee) => (
                <option key={employee.id} value={employee.id}>
                  {employee.display_name}
                </option>
              ))}
            </Select>
          ) : null}
          <Input
            type="date"
            value={dateFrom}
            onChange={(event) => {
              setDateFrom(event.target.value);
              setPage(1);
            }}
          />
          <Input
            type="date"
            value={dateTo}
            onChange={(event) => {
              setDateTo(event.target.value);
              setPage(1);
            }}
          />
          <ButtonSecondary type="button" onClick={resetFilters}>
            重置筛选
          </ButtonSecondary>
        </div>
      </Card>

      {ticketsQuery.isLoading ? (
        <TableSkeleton rows={5} columns={8} />
      ) : null}
      {ticketsQuery.isError ? (
        <ErrorState
          message={
            ticketsQuery.error instanceof Error
              ? ticketsQuery.error.message
              : "加载工单失败"
          }
          onRetry={() => void ticketsQuery.refetch()}
        />
      ) : null}

      {!ticketsQuery.isLoading && !ticketsQuery.isError ? (
        items.length === 0 ? (
          <EmptyState
            title="没有符合条件的工单"
            description="可以调整筛选条件或新建工单。"
          />
        ) : (
          <>
            <Card className="overflow-x-auto p-0">
              <table className="w-full min-w-[980px] text-left text-sm">
                <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-3">编号</th>
                    <th className="px-4 py-3">标题</th>
                    <th className="px-4 py-3">类型</th>
                    <th className="px-4 py-3">优先级</th>
                    <th className="px-4 py-3">状态</th>
                    <th className="px-4 py-3">提交人</th>
                    <th className="px-4 py-3">处理人</th>
                    <th className="px-4 py-3">更新时间</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((ticket) => (
                    <tr
                      key={ticket.id}
                      className="cursor-pointer border-b border-slate-100 last:border-0 hover:bg-slate-50"
                      onClick={() =>
                        router.push(`/tickets/${ticket.id}`)
                      }
                    >
                      <td className="px-4 py-3 font-mono text-xs text-slate-500">
                        {ticket.ticket_no}
                      </td>
                      <td className="px-4 py-3 font-medium text-slate-900">
                        <span className="flex items-center gap-2">
                          {ticket.title}
                          {ticket.is_backfilled ? (
                            <BackfilledBadge />
                          ) : null}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <TicketTypeBadge type={ticket.type} />
                      </td>
                      <td className="px-4 py-3">
                        <TicketPriorityBadge
                          priority={ticket.priority}
                        />
                      </td>
                      <td className="px-4 py-3">
                        <TicketStatusBadge status={ticket.status} />
                      </td>
                      <td className="px-4 py-3">
                        {ticket.created_by.display_name}
                      </td>
                      <td className="px-4 py-3">
                        {ticket.assignee?.display_name ?? "未指派"}
                      </td>
                      <td className="px-4 py-3">
                        {formatDate(ticket.updated_at)}
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
                total={ticketsQuery.data?.total ?? 0}
                onChange={setPage}
              />
            </div>
          </>
        )
      ) : null}
    </div>
  );
}
