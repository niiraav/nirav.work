// webapp/lib/useSession.ts
// Zustand store for session state + WebSocket connection.
// Week 3: wire real WebSocket streaming and append transcript entries.

import { create } from "zustand";
import type { SessionState, WsMessage, Decision } from "./types";

interface SessionStore {
  // Current session
  session: SessionState | null;
  isLoading: boolean;
  error: string | null;

  // Pipeline status
  pipelineStatus: "idle" | "running" | "gate" | "done" | "error";
  currentStage: number;

  // Actions
  loadSession: (sessionId: string) => Promise<void>;
  setSession: (session: SessionState) => void;
  updateTranscript: (entry: WsMessage) => void;
  setPipelineStatus: (status: SessionStore["pipelineStatus"]) => void;
  submitGate: (stage: number, decision: Decision, rationale?: string) => Promise<void>;
}

export const useSession = create<SessionStore>((set, get) => ({
  session: null,
  isLoading: false,
  error: null,
  pipelineStatus: "idle",
  currentStage: 1,

  loadSession: async (sessionId: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`http://localhost:8000/sessions/${sessionId}`);
      const session = (await res.json()) as SessionState;
      set({ session, isLoading: false, currentStage: session.current_stage });
    } catch (e: any) {
      set({ error: e.message, isLoading: false });
    }
  },

  setSession: (session) => set({ session }),

  updateTranscript: (msg) => {
    const { session } = get();
    if (!session) return;
    if (msg.type === "transcript") {
      set({
        session: {
          ...session,
          transcript: [...session.transcript, msg.entry],
        },
      });
    }
    // TODO: handle log, gate, done, error messages
  },

  setPipelineStatus: (status) => set({ pipelineStatus: status }),

  submitGate: async (stage, decision, rationale = "") => {
    const { session } = get();
    if (!session) return;
    await fetch(`http://localhost:8000/sessions/${session.session_id}/gate/${stage}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, rationale }),
    });
    set({ pipelineStatus: "running" });
  },
}));
