export type Role = "employee" | "leader";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
}

export interface UserBrief {
  id: string;
  display_name: string;
  role: Role;
}

export type IndexStatus = "pending" | "indexing" | "ready" | "failed";
export type DocumentAction = "create" | "update" | "delete";
export type DocumentChangeStatus = "pending" | "approved" | "rejected";

export interface DocumentItem {
  id: string;
  title: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  index_status: IndexStatus;
  uploaded_by: UserBrief;
  created_at: string;
  updated_at: string;
}

export interface DocumentChange {
  id: string;
  action: DocumentAction;
  status: DocumentChangeStatus;
  document_id: string | null;
  document_title: string | null;
  title: string | null;
  filename: string | null;
  mime_type: string | null;
  size_bytes: number | null;
  requested_by: UserBrief;
  reviewed_by: UserBrief | null;
  review_comment: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentActionResult {
  mode: "direct" | "pending_approval";
  document: DocumentItem | null;
  change: DocumentChange | null;
}

export interface DownloadResult {
  download_url: string;
  expires_in: number;
}

export interface Citation {
  document_id: string;
  document_title: string;
  chunk_index: number;
  snippet: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[] | null;
  created_at: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export type TicketType =
  | "it_fault"
  | "permission_request"
  | "data_request"
  | "other";

export type TicketPriority = "low" | "medium" | "high" | "urgent";

export type TicketStatus =
  | "new"
  | "pending_assignment"
  | "in_progress"
  | "completed"
  | "pending_user_confirmation"
  | "returned"
  | "modified"
  | "resolved";

export interface TicketAttachment {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  uploaded_by: UserBrief;
  created_at: string;
}

export interface TicketEvent {
  id: number;
  actor: UserBrief;
  action: string;
  from_status: TicketStatus | null;
  to_status: TicketStatus | null;
  comment: string | null;
  created_at: string;
}

export interface TicketSummary {
  id: string;
  ticket_no: string;
  title: string;
  type: TicketType;
  priority: TicketPriority;
  status: TicketStatus;
  is_backfilled: boolean;
  created_by: UserBrief;
  assignee: UserBrief | null;
  created_at: string;
  updated_at: string;
}

export interface TicketDetail extends TicketSummary {
  description: string;
  expected_at: string | null;
  resolution: string | null;
  version: number;
  attachments: TicketAttachment[];
  events: TicketEvent[];
  available_actions: string[];
}

export interface TicketListResponse extends Paginated<TicketSummary> {}
