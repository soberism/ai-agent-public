export type ChecklistItem = { id: string; title: string; completed: boolean; position: number };
export type Checklist = {
  id: string;
  meal_id?: string | null;
  title: string;
  items: ChecklistItem[];
  completed_count: number;
  total_count: number;
  created_at: string;
  updated_at: string;
  source: "app";
  assignee_id: string;
  pinned: boolean;
  shared_household_ids: string[];
};
