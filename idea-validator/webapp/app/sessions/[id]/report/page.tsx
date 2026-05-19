"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const [markdown, setMarkdown] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch(`${API}/sessions/${params.id}/report`)
      .then((r) => (r.ok ? r.json() : Promise.reject(`HTTP ${r.status}`)))
      .then((d) => setMarkdown(d.markdown))
      .catch((e) => setError(String(e)));
  }, [params.id]);

  return (
    <main className="max-w-3xl mx-auto p-8">
      <a href={`/sessions/${params.id}`} className="text-sm text-blue-600 underline mb-6 block">
        ← Back to Session
      </a>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {markdown === null && !error && <p className="text-gray-400 text-sm">Loading report…</p>}
      {markdown && (
        <div className="prose max-w-none">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </div>
      )}
    </main>
  );
}
