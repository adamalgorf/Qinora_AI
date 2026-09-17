export type ApiProblem = {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
};

export type DashboardSummary = {
  kpis: Array<{
    label: string;
    value: string;
    trend: string;
  }>;
  pipeline: Array<{
    status: string;
    count: number;
  }>;
  agentActivity: Array<{
    agent: string;
    event: string;
    confidence: number;
  }>;
};

export type AuthMe = {
  user_id: string;
  tenant_id: string;
  roles: string[];
  full_name: string | null;
};

export type DevTokenPayload = {
  user_id: string;
  tenant_id: string;
  roles: string[];
};

export type TokenResponse = {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: AuthMe;
};

export type AuthConfig = {
  login_required: boolean;
};

export type LoginPayload = {
  email: string;
  password: string;
};

export type ChangePasswordPayload = {
  current_password: string;
  new_password: string;
};

export type UserListItem = {
  id: string;
  email: string;
  full_name: string | null;
  roles: string[];
  is_active: boolean;
};

export type CreateUserPayload = {
  email: string;
  full_name?: string;
  roles: string[];
  temporary_password: string;
};

export type UpdateUserPayload = {
  roles?: string[];
  is_active?: boolean;
};

export type ResetPasswordPayload = {
  temporary_password: string;
};

export type RequestListItem = {
  id: string;
  public_id: string;
  customer: string;
  lane: string;
  mode: string;
  status: string;
  weight_kg: number;
  assignee: string | null;
  sla_due_at: string | null;
  priority: "low" | "normal" | "high" | "critical";
};

export type RequestCargoLineItem = {
  id: string;
  description: string;
  quantity: number | null;
  weight_kg: number | null;
  length_cm: number | null;
  width_cm: number | null;
  height_cm: number | null;
  hazardous: boolean;
  un_number: string | null;
};

export type RequestDetailResponse = {
  request: RequestListItem;
  review_reason: string | null;
  created_at: string;
  cargo_lines: RequestCargoLineItem[];
};

export type ParseFreeTextRequestPayload = {
  customer: string;
  raw_text: string;
};

export type ParseFreeTextRequestResponse = {
  draft: Record<string, unknown>;
  needs_human_review: boolean;
  request: RequestListItem | null;
  agent_confidence: number;
};

export type QuoteListItem = {
  id: string;
  status: string;
  version: number;
  customer_price: number;
  currency: string;
  parent_quote_id: string | null;
  request_id: string | null;
};

export type QuoteLineItem = {
  id: string;
  quote_id: string;
  description: string;
  amount: number;
  currency: string;
};

export type QuoteAcceptanceEventItem = {
  id: string;
  quote_id: string;
  event_type: string;
  detail: string;
  created_at: string;
};

export type SearchResultItem = {
  id: string;
  public_id: string;
  entity_type: string;
  label: string;
  description: string;
  href: string;
};

export type OutboundReplyItem = {
  id: string;
  quote_id: string;
  recipient: string;
  subject: string;
  body_text: string;
  status: string;
  created_at: string;
  sent_at: string | null;
  error_message: string | null;
};

export type SendQuoteResponse = {
  quote: QuoteListItem;
  outbound_reply: OutboundReplyItem;
};

export type QuoteReplyPayload = {
  body_text: string;
  mode?: string;
  total_weight_kg?: number;
  requested_carrier_name?: string;
  min_confidence?: number;
  revised_customer_price?: number;
};

export type QuoteReplyResponse = {
  intent: string;
  event: {
    id: string;
    quote_id: string;
    intent: string;
    body_text: string;
    created_at: string;
  };
  quote: QuoteListItem | null;
  revised_quote: QuoteListItem | null;
  shipment: ShipmentListItem | null;
};

export type AcceptQuotePayload = {
  mode: string;
  total_weight_kg: number;
  requested_carrier_name?: string;
  min_confidence?: number;
};

export type AcceptQuoteResponse = {
  shipment: ShipmentListItem;
  selected_carrier_id: string | null;
  requires_manual_review: boolean;
  overall_confidence: number;
};

export type ShipmentListItem = {
  id: string;
  public_id: string;
  quote_id: string;
  carrier_id: string | null;
  lane: string;
  status: string;
  eta: string;
};

export type InvoiceListItem = {
  id: string;
  public_id: string;
  shipment_id: string;
  quote_id: string;
  invoice_amount: number;
  quote_amount: number;
  currency: string;
  status: string;
  discrepancy_amount: number;
};

export type CarrierListItem = {
  id: string;
  display_name: string;
  modes: string[];
  lane_score: number;
  performance_score: number | null;
  preferred: boolean;
};

export type CarrierCreatePayload = {
  display_name: string;
  modes: string[];
  aliases?: string[];
  email?: string;
  lane_score?: number;
  max_weight_kg?: number;
  performance_score?: number;
  preferred?: boolean;
};

export type ContactListItem = {
  id: string;
  public_id: string;
  display_name: string;
  email: string | null;
  domain: string | null;
  default_markup_percent: number;
  default_incoterms: string | null;
  payment_terms: string | null;
  segment: string | null;
  customer_since: string | null;
  sla_tolerance_hours: number | null;
  account_owner: string | null;
  health_status: "good" | "watch" | "at_risk";
  contract_note: string | null;
  customs_contact_name: string | null;
  customs_contact_email: string | null;
  annual_volume_estimate: number | null;
};

export type CustomerDetailResponse = ContactListItem & {
  active_jobs: number;
  active_route: string | null;
  avg_ai_response_minutes: number | null;
};

export type InboxListItem = {
  id: string;
  sender: string;
  subject: string;
  received_at: string;
  classification: string;
};

export type InboxDetailResponse = {
  message: InboxListItem;
  body_text: string;
};

export type AgentConfigItem = {
  agent_key: string;
  agent_name: string;
  is_enabled: boolean;
  auto_mode: "manual" | "assisted" | "guarded_auto";
  min_confidence: number;
};

export type UpdateAgentConfigPayload = {
  is_enabled: boolean;
  auto_mode: AgentConfigItem["auto_mode"];
  min_confidence: number;
};

export type OperationalTaskItem = {
  id: string;
  entity_type: string;
  entity_id: string;
  priority: string;
  reason: string;
  status: string;
  created_at: string;
};

// --- Documents ---

export type DocumentListItem = {
  id: string;
  public_id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  document_type: string | null;
  status: "pending_review" | "validated" | "manual_review" | "flagged";
  ai_confidence: number | null;
  request_id: string | null;
  shipment_id: string | null;
  contact_id: string | null;
  created_at: string;
};

// --- Cases ---

export type CaseListItem = {
  id: string;
  public_id: string;
  customer: string;
  category: string;
  lane: string;
  priority: "low" | "normal" | "high" | "critical";
  sla_due_at: string | null;
  assignee: string | null;
  status: string;
};

export type CaseActivityItem = {
  type: string;
  timestamp: string;
  tag: string;
  description: string;
};

export type CaseEmailItem = {
  direction: "inbound" | "outbound";
  kind: "customer" | "carrier" | "quote" | "clarification" | "booking_confirmation";
  timestamp: string | null;
  sender: string;
  recipient: string;
  subject: string;
  body_text: string;
};

export type CaseDetailResponse = {
  case: CaseListItem;
  request_detail: RequestDetailResponse;
  quotes: QuoteListItem[];
  shipment: ShipmentListItem | null;
  invoice: InvoiceListItem | null;
  documents: DocumentListItem[];
  contact: ContactListItem | null;
  notes: InternalNoteItem[];
  activity: CaseActivityItem[];
  emails: CaseEmailItem[];
};

export type InternalNoteItem = {
  id: string;
  request_id: string;
  author: string;
  body_text: string;
  created_at: string;
};

export type CreateInternalNotePayload = {
  author: string;
  body_text: string;
};

// --- Automations ---

export type AutomationListItem = {
  agent_key: string;
  agent_name: string;
  trigger: string;
  scope: string;
  success_rate: number;
  volume: number;
  status: "active" | "paused";
};

// --- Analytics ---

export type AnalyticsSummaryResponse = {
  kpis: Array<{ label: string; value: string; trend: string }>;
  workload_by_weekday: Array<{ weekday: string; ai: number; manual: number }>;
  top_exception_categories: Array<{ category: string; percent: number; location: string | null }>;
};

const AUTH_TOKEN_KEY = "qinora.authToken";
const LAST_EMAIL_KEY = "qinora.lastLoginEmail";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_KEY) ?? window.sessionStorage.getItem(AUTH_TOKEN_KEY);
}

/**
 * `remember` picks where the token lives: localStorage survives browser
 * restarts ("Kom ihåg mig på denna enhet"), sessionStorage clears when the
 * tab/window closes - a real difference, not just a decorative checkbox.
 */
export function setAuthToken(token: string, remember = true): void {
  if (remember) {
    window.localStorage.setItem(AUTH_TOKEN_KEY, token);
    window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
  } else {
    window.sessionStorage.setItem(AUTH_TOKEN_KEY, token);
    window.localStorage.removeItem(AUTH_TOKEN_KEY);
  }
}

export function clearAuthToken(): void {
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.sessionStorage.removeItem(AUTH_TOKEN_KEY);
}

export function getLastLoginEmail(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(LAST_EMAIL_KEY) ?? "";
}

export function setLastLoginEmail(email: string): void {
  window.localStorage.setItem(LAST_EMAIL_KEY, email);
}

const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: jsonHeaders(),
  });

  if (!response.ok) {
    throw await toApiProblem(response);
  }

  return (await response.json()) as T;
}

export async function apiPost<TResponse, TPayload>(path: string, payload: TPayload): Promise<TResponse> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await toApiProblem(response);
  }

  return (await response.json()) as TResponse;
}

export async function apiPostVoid<TPayload>(path: string, payload: TPayload): Promise<void> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await toApiProblem(response);
  }
}

export async function apiPatch<TResponse, TPayload>(path: string, payload: TPayload): Promise<TResponse> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw await toApiProblem(response);
  }

  return (await response.json()) as TResponse;
}

export async function apiUpload<TResponse>(path: string, formData: FormData): Promise<TResponse> {
  const token = getAuthToken();
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      accept: "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
    },
    body: formData,
  });

  if (!response.ok) {
    throw await toApiProblem(response);
  }

  return (await response.json()) as TResponse;
}

function jsonHeaders(): HeadersInit {
  const token = getAuthToken();
  return {
    accept: "application/json",
    ...(token ? { authorization: `Bearer ${token}` } : {}),
    "content-type": "application/json",
  };
}

async function toApiProblem(response: Response): Promise<ApiProblem> {
  const payload = (await response.json()) as Partial<ApiProblem> | { detail?: string };
  return {
    type: "about:blank",
    title: "Request failed",
    ...payload,
    status: response.status,
  };
}
