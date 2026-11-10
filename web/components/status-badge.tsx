"use client";

import {
  DOC_ACTION_LABEL,
  DOC_CHANGE_STATUS_LABEL,
  INDEX_STATUS_LABEL,
  TICKET_PRIORITY_LABEL,
  TICKET_STATUS_LABEL,
  TICKET_TYPE_LABEL,
  cn,
} from "@/lib/utils";

import { Badge } from "./ui";

const indexColors: Record<string, string> = {
  pending: "bg-slate-100 text-slate-600",
  indexing: "bg-blue-100 text-blue-700",
  ready: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
};

const actionColors: Record<string, string> = {
  create: "bg-green-100 text-green-700",
  update: "bg-blue-100 text-blue-700",
  delete: "bg-red-100 text-red-700",
};

const changeStatusColors: Record<string, string> = {
  pending: "bg-amber-100 text-amber-700",
  approved: "bg-green-100 text-green-700",
  rejected: "bg-red-100 text-red-700",
};

export function IndexStatusBadge({ status }: { status: string }) {
  return (
    <Badge className={cn(indexColors[status] ?? "bg-slate-100 text-slate-600")}>
      {INDEX_STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function DocumentActionBadge({ action }: { action: string }) {
  return (
    <Badge className={cn(actionColors[action] ?? "bg-slate-100 text-slate-600")}>
      {DOC_ACTION_LABEL[action] ?? action}
    </Badge>
  );
}

export function DocumentChangeStatusBadge({ status }: { status: string }) {
  return (
    <Badge
      className={cn(
        changeStatusColors[status] ?? "bg-slate-100 text-slate-600",
      )}
    >
      {DOC_CHANGE_STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

const ticketStatusColors: Record<string, string> = {
  new: "bg-blue-100 text-blue-700",
  pending_assignment: "bg-amber-100 text-amber-700",
  in_progress: "bg-indigo-100 text-indigo-700",
  completed: "bg-purple-100 text-purple-700",
  pending_user_confirmation: "bg-orange-100 text-orange-700",
  returned: "bg-red-100 text-red-700",
  modified: "bg-cyan-100 text-cyan-700",
  resolved: "bg-green-100 text-green-700",
};

const ticketPriorityColors: Record<string, string> = {
  low: "bg-slate-100 text-slate-600",
  medium: "bg-blue-100 text-blue-700",
  high: "bg-orange-100 text-orange-700",
  urgent: "bg-red-100 text-red-700",
};

const ticketTypeColors: Record<string, string> = {
  it_fault: "bg-red-50 text-red-700",
  permission_request: "bg-blue-50 text-blue-700",
  data_request: "bg-green-50 text-green-700",
  other: "bg-slate-100 text-slate-600",
};

export function TicketStatusBadge({ status }: { status: string }) {
  return (
    <Badge
      className={cn(
        ticketStatusColors[status] ?? "bg-slate-100 text-slate-600",
      )}
    >
      {TICKET_STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function TicketPriorityBadge({
  priority,
}: {
  priority: string;
}) {
  return (
    <Badge
      className={cn(
        ticketPriorityColors[priority] ??
          "bg-slate-100 text-slate-600",
      )}
    >
      {TICKET_PRIORITY_LABEL[priority] ?? priority}
    </Badge>
  );
}

export function TicketTypeBadge({ type }: { type: string }) {
  return (
    <Badge
      className={cn(
        ticketTypeColors[type] ?? "bg-slate-100 text-slate-600",
      )}
    >
      {TICKET_TYPE_LABEL[type] ?? type}
    </Badge>
  );
}

export function BackfilledBadge() {
  return (
    <Badge className="bg-amber-50 text-amber-700">补录</Badge>
  );
}
