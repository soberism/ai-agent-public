export type SharingPolicy = {
  scope: "private" | "household" | "members";
  household_id: string | null;
  member_ids: string[];
};
export type SharingHousehold = {
  id: string;
  name: string;
  role: string;
  members: { account_id: string; display_name: string; role: string }[];
};

export const shareableKinds = [
  "todo",
  "event",
  "checklist",
  "reminder",
  "document",
  "material",
  "folder",
  "meal",
  "shopping",
  "voice_memo",
  "daily_dump",
  "contact",
  "contact_group",
  "pantry",
  "preference",
  "appointment",
];
