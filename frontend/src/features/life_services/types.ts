export type DietaryPreference = { id: string; label: string; kind: string };
export type PantryItem = { id: string; name: string; quantity: number; unit: string };
export type MealPlan = {
  title?: string;
  id: string;
  date: string | null;
  meal_type: string | null;
  diners: number | null;
  schedule_text?: string | null;
  dish: string;
  notes: string | null;
  status: "draft" | "planned";
  calendar_url: string | null;
  shopping_url: string | null;
  preferences: DietaryPreference[];
};
export type ShoppingItem = {
  id: string;
  name: string;
  quantity: number;
  unit: string;
  category: string;
  origin: "generated" | "manual";
  purchased: boolean;
};
export type ShoppingList = {
  id: string;
  meal_id: string | null;
  title: string;
  status: "draft" | "planned";
  checklist_url: string | null;
  items: ShoppingItem[];
};
export type Appointment = {
  id: string;
  patient_name: string;
  institution: string;
  service_type: string;
  preferred_at: string;
  status: "draft" | "planned" | "submitted" | "confirmed" | "cancelled" | "unknown";
  fee_note: string | null;
  external_receipt: string | null;
  calendar_url: string | null;
  todo_url: string | null;
};
export type ServiceCapabilities = {
  delivery: boolean;
  payment: boolean;
  medical_booking: boolean;
};

export const mealTypeLabels: Record<string, string> = {
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  snack: "加餐",
};
