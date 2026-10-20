export type AssistantItem = {
  id: string;
  title: string;
  due_date: string | null;
  due_time: string | null;
  status: string;
  kind: string;
  url: string | null;
};

export type AssistantReply = {
  kind: "result" | "clarify" | "confirm" | "success" | "message";
  message: string;
  items: AssistantItem[];
  action_token: string | null;
  action_label: string | null;
  suggestions?: AgentSuggestion[];
};

export type AgentSuggestion = {
  id: string;
  source_run_id: string;
  label: string;
  type: "follow_up" | "navigate";
  intent: string;
  target_kind: "todo" | "event" | "reminder" | "checklist";
  target_id: string;
  target_title: string;
  draft: string | null;
  url: string | null;
};

export type ChatEntry =
  { role: "user"; message: string } | { id?: string; role: "assistant"; reply: AssistantReply };

export type AssistantThread = { thread_id: string; expires_at: string; entries: ChatEntry[] };

export type AgentRunStatus =
  "queued" | "running" | "waiting" | "completed" | "failed" | "cancelled";

export type AgentSource = {
  title: string;
  excerpt: string | null;
  url: string | null;
  chunk_id?: string | null;
  document_version?: string | null;
  locator?: { char_offset?: number } | null;
};

export type AgentAction = {
  id: string;
  title: string;
  description: string | null;
  status: "proposed" | "approved" | "executing" | "completed" | "failed" | "cancelled";
  result: AssistantReply | null;
  error: string | null;
};

export type AgentRun = {
  id: string;
  thread_id: string;
  prompt?: string;
  parent_plan_id?: string | null;
  status: AgentRunStatus;
  progress: string | null;
  final_answer: string | null;
  sources: AgentSource[];
  actions: AgentAction[];
  plan_version: number | null;
  error: string | null;
  suggestions?: AgentSuggestion[];
};

export type AssistantPreferences = {
  custom_instructions: string;
  memory_enabled: boolean;
  updated_at: string | null;
};

export type AssistantMemory = {
  id: string;
  content: string;
  source: "user" | "assistant";
  enabled: boolean;
  created_at: string;
  updated_at: string;
};
