// webapp/lib/useSession.ts
// Zustand store for session state + WebSocket connection.

import { create } from "zustand";
import type {
  SessionState,
  GateData,
  GateDecisionRequest,
  TranscriptEntry,
} from "./types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_API = API.replace(/^http/, "ws");

type Status = "idle" | "running" | "gate" | "done" | "error";

interface SessionStore {
  session:      SessionState | null;
  status:       Status;
  pendingGate:  { stage: number; gate_data: GateData } | null;
  logs:         string[];
  error:        string | null;

  loadSession:   (id: string) => Promise<void>;
  startPipeline: (id: string, stage?: number) => Promise<void>;
  submitGate:    (id: string, stage: number, d: GateDecisionRequest) => Promise<void>;
  connectWs:     (id: string) => void;
  disconnectWs:  () => void;
}

let _ws: WebSocket | null = null;
let _reconnectAttempts = 0;

function appendEntry(session: SessionState | null, entry: TranscriptEntry): SessionState | null {
  if (!session) return session;
  return { ...session, transcript: [...session.transcript, entry] };
}

export const useSession = create<SessionStore>((set, get) => ({
  session:     null,
  status:      "idle",
  pendingGate: null,
  logs:        [],
  error:       null,

  loadSession: async (id) => {
    try {
      const res = await fetch(`${API}/sessions/${id}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const session = (await res.json()) as SessionState;
      set({ session });
    } catch (e: any) {
      set({ error: e.message });
    }
  },

  startPipeline: async (id, stage = 1) => {
    set({ status: "running", logs: [], pendingGate: null, error: null });
    await fetch(`${API}/sessions/${id}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ stage }),
    });
  },

  submitGate: async (id, stage, d) => {
    set({ pendingGate: null, status: "running" });
    await fetch(`${API}/sessions/${id}/gate/${stage}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(d),
    });
  },

  connectWs: (id) => {
    if (_ws) {
      _ws.close();
      _ws = null;
    }
    _reconnectAttempts = 0;

    function connect() {
      const ws = new WebSocket(`${WS_API}/sessions/${id}/stream`);
      _ws = ws;

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case "state":
            set({ session: msg.session });
            break;
          case "log":
            set((s) => ({ logs: [...s.logs, msg.text] }));
            break;
          case "transcript":
            set((s) => ({ session: appendEntry(s.session, msg.entry) }));
            break;
          case "gate":
            set({ status: "gate", pendingGate: msg });
            break;
          case "done":
            set({ status: "done", pendingGate: null });
            break;
          case "error":
            set({ status: "error", error: msg.message });
            break;
        }
      };

      ws.onclose = () => {
        const { status } = get();
        if (status === "running" && _reconnectAttempts < 5) {
          _reconnectAttempts++;
          setTimeout(connect, 2000);
        }
      };
    }

    connect();
  },

  disconnectWs: () => {
    if (_ws) {
      _ws.close();
      _ws = null;
    }
  },
}));
