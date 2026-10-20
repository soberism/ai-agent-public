import type { Todo } from "../todos/types";
import type { CalendarEvent } from "../calendar/types";

export type HubSummary = {
  pending_reviews: number;
  pending_assignments: number;
  failed_emails: number;
  connection_issues: number;
  pending_voice_memos: number;
};

export type PlatformSettings = {
  id: string;
  email: string;
  nickname: string | null;
  timezone: string;
  has_todos: boolean;
};

export type PlatformHome = {
  timezone: string;
  server_time: string;
  today: { count: number; items: Todo[] };
  overdue: { count: number; items: Todo[] };
  recent: Todo[];
  recent_events: CalendarEvent[];
};
