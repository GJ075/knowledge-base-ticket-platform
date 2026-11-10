export type Role = "employee" | "leader";

export interface User {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  can_evaluate: boolean;
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

export interface TrashDocument extends DocumentItem {
  deleted_at: string;
}

export interface BatchItem {
  id: string;
  title: string;
}

export interface SkippedItem {
  id: string;
  title?: string | null;
  reason: string;
}

export interface BatchDeleteResult {
  mode: "direct" | "pending_approval";
  deleted: BatchItem[];
  submitted: BatchItem[];
  skipped: SkippedItem[];
}

export interface BatchResult {
  processed: BatchItem[];
  skipped: SkippedItem[];
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

export type EvalExpectedType = "answerable" | "unanswerable";
export type EvalRetrievalMode = "question" | "rewritten";
export type EvalRunStatus =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
export type EvalItemStatus =
  | "pending"
  | "running"
  | "passed"
  | "failed"
  | "invalid"
  | "error"
  | "cancelled";

export interface EvalDocumentRef {
  id: string;
  title: string;
}

export interface EvalTurn {
  id: string;
  turn_index: number;
  question: string;
  reference_answer: string | null;
  expected_type: EvalExpectedType;
  required_document_ids: string[];
  required_documents: EvalDocumentRef[];
}

export interface EvalCase {
  id: string;
  title: string;
  tags: string[];
  sort_order: number;
  turns: EvalTurn[];
}

export interface EvalRunSummary {
  id: string;
  status: EvalRunStatus;
  retrieval_mode: EvalRetrievalMode;
  total_items: number;
  completed_items: number;
  created_at: string;
  finished_at: string | null;
}

export interface EvalDataset {
  id: string;
  name: string;
  description: string | null;
  is_archived: boolean;
  case_count: number;
  turn_count: number;
  created_at: string;
  updated_at: string;
  last_run: EvalRunSummary | null;
}

export interface EvalDatasetDetail extends EvalDataset {
  cases: EvalCase[];
}

export interface EvalRun {
  id: string;
  dataset_id: string;
  dataset_name: string;
  retrieval_mode: EvalRetrievalMode;
  status: EvalRunStatus;
  baseline_run_id: string | null;
  total_items: number;
  completed_items: number;
  metrics: Record<string, number | null> | null;
  error: string | null;
  created_by: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  progress: number;
}

export interface EvalRetrieved {
  document_id: string;
  document_title: string;
  chunk_index: number;
  snippet: string;
}

export interface EvalRunItem {
  id: number;
  case_id: string;
  case_title: string;
  turn_index: number;
  question: string;
  reference_answer: string | null;
  expected_type: EvalExpectedType;
  required_document_ids: string[];
  status: EvalItemStatus;
  retrieval_query: string | null;
  retrieved: EvalRetrieved[] | null;
  citations: EvalRetrieved[] | null;
  answer: string | null;
  judge_score: number | null;
  judge_passed: boolean | null;
  refused: boolean | null;
  judge_reason: string | null;
  retrieval_hit: boolean | null;
  retrieval_recall: number | null;
  retrieval_rank: number | null;
  citation_hit: boolean | null;
  citation_precision: number | null;
  passed: boolean | null;
  invalid_reason: string | null;
  error: string | null;
  latency_ms: number | null;
}

export interface EvalCompare {
  current: EvalRun;
  baseline: EvalRun;
  metric_delta: Record<string, number>;
  case_changes: {
    newly_failed: { case_id: string; case_title: string; turn_index: number; status: string }[];
    newly_passed: { case_id: string; case_title: string; turn_index: number; status: string }[];
  };
}

export interface EvalPermission {
  id: string;
  username: string;
  display_name: string;
  role: Role;
  can_evaluate: boolean;
}

export interface EvalTurnInput {
  question: string;
  reference_answer: string | null;
  expected_type: EvalExpectedType;
  required_document_ids: string[];
}

export interface EvalCaseInput {
  title: string;
  tags: string[];
  turns: EvalTurnInput[];
}
