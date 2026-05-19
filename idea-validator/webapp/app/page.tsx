"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { SessionSummary } from "../lib/types";
import ManifestUpload from "../components/ManifestUpload";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function HomePage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [showUpload, setShowUpload] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/sessions`)
      .then((r) => r.json())
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  function handleCreated(sessionId: string) {
    setShowUpload(false);
    router.push(`/sessions/${sessionId}`);
  }

  return (
    <main className="max-w-3xl mx-auto p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-3xl font-bold">Idea Validator</h1>
          <p className="text-gray-500 text-sm mt-1">
            Dual-agent deliberation — Synthesizer vs Skeptic
          </p>
        </div>
        <button
          onClick={() => setShowUpload((v) => !v)}
          className="px-4 py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700"
        >
          + New Session
        </button>
      </div>

      {showUpload && (
        <div className="border rounded-xl mb-6 shadow-sm">
          <ManifestUpload onCreated={handleCreated} />
        </div>
      )}

      <div className="space-y-2">
        <h2 className="text-lg font-semibold text-gray-700 mb-3">Sessions</h2>
        {loading && (
          <p className="text-sm text-gray-400">Loading…</p>
        )}
        {!loading && sessions.length === 0 && (
          <p className="text-sm text-gray-400">
            No sessions yet — click "+ New Session" to start.
          </p>
        )}
        {sessions.map((s) => (
          <a
            key={s.session_id}
            href={`/sessions/${s.session_id}`}
            className="flex items-center justify-between p-4 border rounded-lg hover:bg-gray-50 transition-colors"
          >
            <div>
              <div className="font-mono text-sm text-gray-800">{s.session_id}</div>
              {s.approved_niche && (
                <div className="text-xs text-blue-600 mt-0.5">{s.approved_niche}</div>
              )}
            </div>
            <div className="text-right text-xs text-gray-500">
              <div>Stage {s.current_stage} / 5</div>
              <div>{new Date(s.created_at).toLocaleDateString()}</div>
            </div>
          </a>
        ))}
      </div>
    </main>
  );
}
