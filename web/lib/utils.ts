import { clsx, type ClassValue } from "clsx";
import { format } from "date-fns";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return format(date, "yyyy-MM-dd HH:mm");
}

export const DOC_ACTION_LABEL: Record<string, string> = {
  create: "新增",
  update: "修改",
  delete: "删除",
};

export const DOC_CHANGE_STATUS_LABEL: Record<string, string> = {
  pending: "待审批",
  approved: "已通过",
  rejected: "已驳回",
};

export const INDEX_STATUS_LABEL: Record<string, string> = {
  pending: "待索引",
  indexing: "索引中",
  ready: "可检索",
  failed: "索引失败",
};

export const TICKET_TYPE_LABEL: Record<string, string> = {
  it_fault: "IT故障",
  permission_request: "权限申请",
  data_request: "资料申请",
  other: "其他",
};

export const TICKET_PRIORITY_LABEL: Record<string, string> = {
  low: "低",
  medium: "中",
  high: "高",
  urgent: "紧急",
};

export const TICKET_STATUS_LABEL: Record<string, string> = {
  new: "新建上传",
  pending_assignment: "待分配",
  in_progress: "处理中",
  completed: "处理完成",
  pending_user_confirmation: "待用户确认",
  returned: "回退员工修改",
  modified: "修改完成",
  resolved: "已解决",
};

export const TICKET_EVENT_LABEL: Record<string, string> = {
  created: "创建工单",
  backfilled: "补录工单",
  approved: "审核通过",
  rejected: "审核不通过",
  assigned: "指派处理人",
  marked_completed: "标记处理完成",
  confirmed_resolved: "确认已解决",
  confirmed_unresolved: "确认未解决",
  marked_modified: "标记修改完成",
  edited: "编辑工单",
};

export const TICKET_ACTION_LABEL: Record<string, string> = {
  approve: "审核通过",
  reject: "审核不通过",
  assign: "指派处理人",
  complete: "标记处理完成",
  modify_complete: "标记修改完成",
  confirm_resolved: "确认已解决",
  confirm_unresolved: "确认未解决",
  edit: "编辑工单",
  add_attachment: "添加附件",
  delete_attachment: "删除附件",
};
