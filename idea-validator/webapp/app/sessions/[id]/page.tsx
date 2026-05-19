"use client";

import { useEffect } from "react";
import { useParams } from "next/navigation";
import { useSession } from "../../../lib/useSession";
import StageProgress from "../../../components/StageProgress";
import TranscriptPanel from "../../../components/TranscriptPanel";
import GateCard from "../../../components/GateCard";
import type { GateDecisionRequest } from "../../../lib/types";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function SessionPage() {
  const params = useParams<{ id: string }>();
  const {
    session, status, pendingGate, logs, error,
    loadSession, startPipeline, submitGate, connectWs, disconnectWs,
  } = useSession();

  useEffect(() => {
    if (!params.id) return;
    loadSession(params.id);
    connectWs(params.id);
    return () => disconnectWs();
  }, [params.id]);

  function handleDecide(d: GateDecisionRequest) {
    if (!pendingGate || !params.id) return;
    submitGate(params.id, pendingGate.stage, d);
  }

  return (
    <main className="max-w-5xl mx-auto">
      <div className="sticky top-0 bg-white z-10 border-b">
        <StageProgress
          currentStage={session?.current_stage ?? 1}
          status={status}
        />
      </div>

      {/* Log stream (collapsed) */}
      {logs.length > 0 && status === "running" && (
        <details className="mx-4 mt-3">
          <summary className="text-xs text-gray-500 cursor-pointer">
            Pipeline logs ({logs.length})
          </summary>
          <pre className="text-xs bg-gray-50 p-2 rounded mt-1 max-h-32 overflow-y-auto whitespace-pre-wrap">
            {logs.join("\n")}
          </pre>
        </details>
      )}

      {error && (
        <div className="mx-4 mt-3 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      <TranscriptPanel
        entries={session?.transcript ?? []}
        isRunning={status === "running"}
      />

      {pendingGate && (
        <GateCard
          stage={pendingGate.stage}
          gateData={pendingGate.gate_data}
          onDecide={handleDecide}
        />
      )}

      {status === "idle" && session && (
        <div className="p-4">
          <button
            onClick={() => startPipeline(params.id, session.current_stage)}
            className="px-6 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700"
          >
            {session.current_stage > 1
              ? `Resume from Stage ${session.current_stage}`
              : "Start Pipeline"}
          </button>
        </div>
      )}

      {status === "done" && (
        <div className="p-4 text-center">
          <p className="text-green-700 font-semibold mb-2">Pipeline complete</p>
          <a
            href={`${API}/sessions/${params.id}/report`}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-blue-600 underline"
          >
            View report
          </a>
        </div>
      )}
    </main>
  );
}
