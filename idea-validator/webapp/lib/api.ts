// webapp/lib/api.ts
// REST client stubs — point to FastAPI backend (or MSW in dev).

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function _fetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`API ${res.status}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // Sessions
  listSessions: () => _fetch<Array<import("./types").SessionSummary>>("/sessions"),

  getSession: (id: string) =>
    _fetch<import("./types").SessionState>(`/sessions/${id}`),

  createSession: (req: import("./types").CreateSessionRequest) =>
    _fetch<import("./types").SessionSummary>("/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    }),

  deleteSession: (id: string) =>
    fetch(`${API_BASE}/sessions/${id}`, { method: "DELETE" }),

  // Pipeline
  runSession: (id: string) =>
    _fetch<{ status: string; session_id: string }>(`/sessions/${id}/run`, {
      method: "POST",
    }),

  submitGate: (id: string, stage: number, req: import("./types").GateDecisionRequest) =>
    _fetch<{ status: string; decision: string; stage: number }>(
      `/sessions/${id}/gate/${stage}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(req),
      }
    ),

  getReport: (id: string) =>
    _fetch<{ markdown: string }>(`/sessions/${id}/report`),

  // Manifest validation
  validateManifest: (manifest: import("./types").Manifest) =>
    _fetch<{ valid: boolean; errors: string[] }>("/sessions/validate-manifest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(manifest),
    }),
};
