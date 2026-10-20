export type DocumentFolder = { id: string; name: string; count: number; editable?: boolean };
export type DocumentCapabilities = {
  email: boolean;
  local_upload: boolean;
  text_extraction: boolean;
};

export type SourceMaterial = {
  id: string;
  name: string;
  kind: "file" | "photo" | "email" | "voice";
  status: "uploaded" | "processing" | "ready" | "partial" | "failed";
  created_at: string;
  folder_id: string | null;
  error_message: string | null;
  review_count: number;
};

export type ReviewItem = {
  id: string;
  material_id: string;
  material_name: string;
  target_type: "todo" | "event" | "checklist" | "reminder" | "document";
  title: string;
  evidence: string;
  confidence: number;
  status: "pending" | "accepted" | "ignored" | "failed";
  target_url: string | null;
  change_kind?: "duplicate" | "changed" | "cancelled" | null;
  previous_value?: string | null;
};
