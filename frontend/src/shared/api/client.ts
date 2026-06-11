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

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, {
    headers: { accept: "application/json" },
  });

  if (!response.ok) {
    throw (await response.json()) as ApiProblem;
  }

  return (await response.json()) as T;
}
