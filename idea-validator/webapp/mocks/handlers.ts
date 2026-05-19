// webapp/mocks/handlers.ts
// Mock Service Worker handlers — serve the session fixture for dev.
// Activated via NEXT_PUBLIC_MSW=true in .env.local.
// Uses absolute URLs so MSW intercepts fetch() calls that use the API_BASE.

import { http, HttpResponse } from "msw";
import fixture from "./session-fixture.json";
import type { SessionSummary, SessionState } from "../lib/types";

const API_BASE = "http://localhost:8000";

function toSummary(raw: SessionState): SessionSummary {
  return {
    session_id: raw.session_id,
    created_at: raw.created_at,
    current_stage: raw.current_stage,
    niche_hint: raw.niche_hint,
    approved_niche: raw.approved_niche ?? null,
    approved_pain_point: raw.approved_pain_point ?? null,
    approved_solution: raw.approved_solution ?? null,
  };
}

export const handlers = [
  http.get(`${API_BASE}/sessions`, () => HttpResponse.json([toSummary(fixture as unknown as SessionState)])),

  http.get(`${API_BASE}/sessions/:id`, () => HttpResponse.json(fixture)),

  http.post(`${API_BASE}/sessions`, async ({ request }) => {
    const body = (await request.json()) as { niche_hint?: string };
    return HttpResponse.json(
      {
        session_id: `mock-${Date.now()}`,
        created_at: new Date().toISOString(),
        current_stage: 1,
        niche_hint: body.niche_hint ?? "",
        approved_niche: null,
        approved_pain_point: null,
        approved_solution: null,
      },
      { status: 201 }
    );
  }),

  http.post(`${API_BASE}/sessions/:id/run`, () =>
    HttpResponse.json({ status: "started" }, { status: 202 })
  ),

  http.post(`${API_BASE}/sessions/:id/gate/:stage`, async ({ request }) => {
    const body = (await request.json()) as { decision: string };
    return HttpResponse.json({ status: "ok", decision: body.decision });
  }),

  http.get(`${API_BASE}/sessions/:id/report`, () =>
    HttpResponse.json({ markdown: "# Stub Report\n\nValidation complete." })
  ),

  http.post(`${API_BASE}/sessions/validate-manifest`, () =>
    HttpResponse.json({ valid: true, errors: [] })
  ),
];
