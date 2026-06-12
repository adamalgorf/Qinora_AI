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

export type RequestListItem = {
  id: string;
  public_id: string;
  customer: string;
  lane: string;
  mode: string;
  status: string;
  weight_kg: number;
};

export type CreateRequestPayload = {
  customer: string;
  origin: string;
  destination: string;
  mode: "ftl" | "ltl" | "ocean" | "air" | "rail" | "intermodal";
  loading_time?: string;
  unloading_time?: string;
  cargo: Array<{
    description: string;
    quantity?: number;
    weight_kg?: number;
    length_cm?: number;
    width_cm?: number;
    height_cm?: number;
  }>;
};

export type CreateRequestResponse = {
  request: RequestListItem;
  complete: boolean;
  review_reason: string | null;
  adr_un_numbers: string[];
};

export type QuoteListItem = {
  id: string;
  status: string;
  version: number;
  customer_price: number;
  currency: string;
  parent_quote_id: string | null;
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

export type QuoteDetailResponse = {
  quote: QuoteListItem;
  line_items: QuoteLineItem[];
  acceptance_events: QuoteAcceptanceEventItem[];
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

export type ProcessOutboundQueueResponse = {
  sent: OutboundReplyItem[];
  failed: OutboundReplyItem[];
};

export type CreateQuotePayload = {
  request_id: string;
  customer_price: number;
  currency: string;
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

export type CreateInvoicePayload = {
  invoice_amount: number;
  max_discrepancy?: number;
};

export type CreateInvoiceResponse = {
  invoice: InvoiceListItem;
  shipment_status: string;
};

export type RunTrackingSimulatorResponse = {
  delivered: ShipmentListItem[];
  invoices: InvoiceListItem[];
};

export type UpdateShipmentStatusPayload = {
  status: string;
};

export type OverrideShipmentPayload = {
  status: string;
  reason: string;
};

export type CarrierListItem = {
  id: string;
  display_name: string;
  modes: string[];
  lane_score: number;
  performance_score: number | null;
  preferred: boolean;
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
};

export type InboxListItem = {
  id: string;
  sender: string;
  subject: string;
  received_at: string;
  classification: string;
};

export type AgentLogListItem = {
  agent_key: string;
  agent_name: string;
  step: string;
  entity_id: string;
  confidence: number;
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

export type ShipmentEventItem = {
  id: string;
  shipment_id: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  created_at: string;
};

const AUTH_TOKEN_KEY = "qinora.authToken";

export function getAuthToken(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: jsonHeaders(),
  });

  if (!response.ok) {
    throw (await response.json()) as ApiProblem;
  }

  return (await response.json()) as T;
}

export async function apiPost<TResponse, TPayload>(path: string, payload: TPayload): Promise<TResponse> {
  const response = await fetch(`/api${path}`, {
    method: "POST",
    headers: jsonHeaders(),
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw (await response.json()) as ApiProblem;
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
