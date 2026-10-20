export type HouseholdSummary = {
  id: string;
  name: string;
  role: string;
  member_count: number;
};

export type HouseholdMember = {
  id: string;
  account_id: string | null;
  display_name: string;
  email: string;
  role: string;
  permissions: string[];
  status: string;
};

export type Invitation = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string | null;
};

export type ManagedProfile = {
  id: string;
  name: string;
  relationship: string;
  birth_date: string | null;
};

export type Pet = {
  id: string;
  name: string;
  species: string;
  breed: string | null;
};

export type HouseholdDetail = HouseholdSummary & {
  members: HouseholdMember[];
  invitations: Invitation[];
  profiles: ManagedProfile[];
  pets: Pet[];
};

export type Contact = {
  id: string;
  name: string;
  relationship: string;
  phone: string | null;
  email: string | null;
  group_ids: string[];
};

export type ContactGroup = {
  id: string;
  name: string;
  contact_ids: string[];
};

export type NotificationItem = {
  id: string;
  type: string;
  title: string;
  message: string;
  read: boolean;
  created_at: string;
  invitation_id: string | null;
};
