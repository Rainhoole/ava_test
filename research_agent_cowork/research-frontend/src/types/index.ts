export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';

export type PaymentStatus = 'pending' | 'authorized' | 'processing' | 'completed' | 'failed' | 'skipped';

export type Engine = 'claude' | 'openai';

export interface Task {
  task_id: string;
  handle: string;
  status: TaskStatus;
  version: string;
  engine: Engine;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  message_count: number;
  cost_usd: number;
  error_message?: string;
  // Payment fields
  mandate_id?: string;
  budget_usd: number;
  payment_status: PaymentStatus;
  payment_amount_usd: number;
  tool_calls: number;
  payment_error?: string;
  payment_tx_hash?: string;
}

export interface TaskListResponse {
  tasks: Task[];
  total: number;
}

export interface ResearchRequest {
  handle: string;
  engine?: Engine;
  model?: string;
  mandate_id?: string;
  budget_usd?: number;
  fluxa_jwt?: string;
}

export interface PaymentDetails {
  task_id: string;
  payment_status: PaymentStatus;
  budget_usd: number;
  claude_cost_usd: number;
  tool_calls: number;
  tool_cost_usd: number;
  total_cost_usd: number;
  payment_amount_usd: number;
  payment_tx_hash?: string;
  payment_error?: string;
}

export interface ReportResponse {
  task_id: string;
  handle: string;
  status: string;
  report?: {
    content: string;
    filename: string;
    size_bytes: number;
  };
}

export interface ReportMetadata {
  score?: number;
  stage?: string;
  confidence?: string;
  categories: string[];
}

export interface SourceItem {
  id: string;
  label: string;
  url: string;
  domain: string;
}

export interface ScoreBreakdownItem {
  label: string;
  score: number;
  max: number;
  percentage: number;
}

export interface TimelineEvent {
  date: string;
  event: string;
  category: 'product' | 'milestone' | 'announcement' | 'unknown';
}

export interface StructuredSection {
  id: string;
  title: string;
  tldr?: string;
  blocks: string[];
  markdown: string;
  wordCount: number;
}

export interface StructuredReport {
  title: string;
  handle?: string;
  normalizedContent: string;
  metadata: ReportMetadata;
  sections: StructuredSection[];
  scoring: ScoreBreakdownItem[];
  timeline: TimelineEvent[];
  sources: SourceItem[];
  totalWords: number;
  readingMinutes: number;
}

// ==================== Structured Log Types ====================

/**
 * All possible log entry types from the JSONL log file.
 */
export type LogEntryType =
  | 'session_start'
  | 'session_end'
  | 'app'
  | 'user_message'
  | 'user_text'
  | 'user_block'
  | 'assistant_text'
  | 'assistant_thinking'
  | 'tool_call'
  | 'tool_result'
  | 'system'
  | 'budget'
  | 'result'
  | 'stream_event'
  | 'error'
  | 'unknown'
  | 'unknown_block';

/**
 * Base log entry structure (all entries have these fields).
 */
export interface BaseLogEntry {
  type: LogEntryType;
  ts: string;       // Timestamp HH:MM:SS
  seq: number;      // Sequence number
}

/**
 * Session start entry - marks the beginning of a research session.
 */
export interface SessionStartEntry extends BaseLogEntry {
  type: 'session_start';
  target: string;
  version: string;
  model: string;
  started_at: string;
  skill?: string;
}

/**
 * Session end entry - marks completion of a research session.
 */
export interface SessionEndEntry extends BaseLogEntry {
  type: 'session_end';
  success: boolean;
  duration_seconds: number;
  message_count: number;
  cost_usd: number;
  error?: string | null;
}

/**
 * Application log entry - logs from the Python program itself.
 */
export interface AppLogEntry extends BaseLogEntry {
  type: 'app';
  level: 'info' | 'warn' | 'error' | 'debug';
  message: string;
}

/**
 * User message entry - text from user.
 */
export interface UserMessageEntry extends BaseLogEntry {
  type: 'user_message' | 'user_text';
  content: string;
}

/**
 * User block entry - unknown block type in user message.
 */
export interface UserBlockEntry extends BaseLogEntry {
  type: 'user_block';
  block_type: string;
  raw: string;
}

/**
 * Assistant text entry - Claude's text response.
 */
export interface AssistantTextEntry extends BaseLogEntry {
  type: 'assistant_text';
  model: string;
  content: string;
}

/**
 * Assistant thinking entry - Claude's reasoning/thinking process.
 */
export interface AssistantThinkingEntry extends BaseLogEntry {
  type: 'assistant_thinking';
  model: string;
  content: string;
}

/**
 * Tool call entry - Claude requesting to use a tool.
 */
export interface ToolCallEntry extends BaseLogEntry {
  type: 'tool_call';
  model: string;
  tool: string;
  tool_use_id: string;
  input: Record<string, unknown>;
}

/**
 * Tool result entry - result from tool execution.
 */
export interface ToolResultEntry extends BaseLogEntry {
  type: 'tool_result';
  tool_use_id: string;
  is_error: boolean;
  output: string;
  model?: string;
}

/**
 * System message entry.
 */
export interface SystemEntry extends BaseLogEntry {
  type: 'system';
  subtype: string;
  data: Record<string, unknown>;
}

/**
 * Budget authorization entry - frontend-only UI steps.
 */
export interface BudgetAction {
  id: string;
  label: string;
  variant?: 'primary' | 'secondary' | 'ghost';
  disabled?: boolean;
  onClick?: () => void;
}

export interface BudgetEntry extends BaseLogEntry {
  type: 'budget';
  role: 'assistant' | 'user' | 'system';
  content: string;
  actions?: BudgetAction[];
}

/**
 * Result message entry - final result from Claude Agent SDK.
 */
export interface ResultEntry extends BaseLogEntry {
  type: 'result';
  subtype: string;
  session_id: string;
  is_error: boolean;
  num_turns: number;
  duration_ms: number;
  duration_api_ms: number;
  cost_usd: number | null;
  usage: Record<string, unknown> | null;
  result: string | null;
  structured_output: unknown | null;
}

/**
 * Stream event entry.
 */
export interface StreamEventEntry extends BaseLogEntry {
  type: 'stream_event';
  uuid: string;
  session_id: string;
  event_type: string;
  event: Record<string, unknown>;
  parent_tool_use_id: string | null;
}

/**
 * Error entry.
 */
export interface ErrorEntry extends BaseLogEntry {
  type: 'error';
  message: string;
}

/**
 * Unknown message/block entries for forward compatibility.
 */
export interface UnknownEntry extends BaseLogEntry {
  type: 'unknown' | 'unknown_block';
  message_type?: string;
  block_type?: string;
  raw: string;
  model?: string;
}

/**
 * Union type of all log entries.
 */
export type LogEntry =
  | SessionStartEntry
  | SessionEndEntry
  | AppLogEntry
  | UserMessageEntry
  | UserBlockEntry
  | AssistantTextEntry
  | AssistantThinkingEntry
  | ToolCallEntry
  | ToolResultEntry
  | SystemEntry
  | BudgetEntry
  | ResultEntry
  | StreamEventEntry
  | ErrorEntry
  | UnknownEntry;
