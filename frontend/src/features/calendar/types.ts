export type CalendarEvent = {
  id: string;
  title: string;
  description: string | null;
  location: string | null;
  todo_id: string | null;
  series_id: string | null;
  source: string;
  status: "scheduled" | "cancelled";
  assignee_id: string;
  start_date: string;
  start_time: string;
  end_date: string;
  end_time: string;
  timezone: string;
  starts_at: string;
  ends_at: string;
  created_at: string;
  updated_at: string;
};

export type EventValues = {
  title: string;
  description: string;
  location: string;
  start_date: string;
  start_time: string;
  end_date: string;
  end_time: string;
  todo_id: string | null;
  recurrence: "none" | "daily" | "weekly";
  recurrence_until: string;
  status: "scheduled" | "cancelled";
};

export const valuesOf = (event?: CalendarEvent | null): EventValues => ({
  title: event?.title ?? "",
  description: event?.description ?? "",
  location: event?.location ?? "",
  start_date: event?.start_date ?? "",
  start_time: event?.start_time ?? "09:00",
  end_date: event?.end_date ?? "",
  end_time: event?.end_time ?? "10:00",
  todo_id: event?.todo_id ?? null,
  recurrence: "none",
  recurrence_until: "",
  status: event?.status ?? "scheduled",
});

export const eventPayload = (values: EventValues) => ({
  ...values,
  recurrence_until: values.recurrence_until || null,
});
