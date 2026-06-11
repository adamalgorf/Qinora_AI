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

export type RequestListItem = {
  id: string;
  public_id: string;
  customer: string;
  lane: string;
  mode: string;
  status: string;
  weight_kg: number;
};

export type QuoteListItem = {
  id: string;
  status: string;
  version: number;
  customer_price: number;
  currency: string;
  parent_quote_id: string | null;
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

export type CarrierListItem = {
  id: string;
  display_name: string;
  modes: string[];
  lane_score: number;
  performance_score: number | null;
  preferred: boolean;
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

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { accept: "application/json" },
  });

  if (!response.ok) {
    throw (await response.json()) as ApiProblem;
  }

  return (await response.json()) as T;
}
