"use client";

import { useState, type FC, type ChangeEvent } from "react";
import type { Manifest } from "../lib/types";

interface Props {
  onCreated: (sessionId: string) => void;
}

const ManifestUpload: FC<Props> = ({ onCreated }) => {
  const [mode, setMode] = useState<"upload" | "paste">("paste");
  const [jsonText, setJsonText] = useState("");
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [isValid, setIsValid] = useState(false);
  const [nicheHint, setNicheHint] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [parseError, setParseError] = useState("");

  const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  async function handleValidate(text: string) {
    setParseError("");
    setValidationErrors([]);
    setIsValid(false);

    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setParseError("Invalid JSON — check syntax");
      return;
    }

    const res = await fetch(`${API}/sessions/validate-manifest`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(parsed),
    });

    if (res.ok) {
      const data = await res.json();
      if (data.valid) {
        setIsValid(true);
      } else {
        setValidationErrors(data.errors ?? ["Unknown validation error"]);
      }
    } else {
      const data = await res.json().catch(() => ({}));
      const detail = data.detail;
      if (Array.isArray(detail)) {
        setValidationErrors(detail.map((e: any) => `${e.loc?.join(".")} — ${e.msg}`));
      } else {
        setValidationErrors([String(detail ?? "Validation failed")]);
      }
    }
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const text = (ev.target?.result as string) ?? "";
      setJsonText(text);
      handleValidate(text);
    };
    reader.readAsText(file);
  }

  async function handleStart() {
    if (!isValid) return;
    setIsSubmitting(true);
    try {
      const manifest = JSON.parse(jsonText);
      const res = await fetch(`${API}/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ manifest, niche_hint: nicheHint }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const session = await res.json();
      onCreated(session.session_id);
    } catch (e: any) {
      setValidationErrors([e.message]);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="space-y-4 p-4">
      <h2 className="text-lg font-semibold">New Session</h2>

      {/* Mode tabs */}
      <div className="flex gap-2">
        {(["paste", "upload"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`px-3 py-1 text-sm rounded-md ${
              mode === m ? "bg-blue-600 text-white" : "bg-gray-100 text-gray-600"
            }`}
          >
            {m === "paste" ? "Paste JSON" : "Upload File"}
          </button>
        ))}
      </div>

      {mode === "paste" ? (
        <textarea
          className="w-full border rounded p-2 text-xs font-mono h-48 resize-none"
          placeholder='{"lead_segments": {...}, ...}'
          value={jsonText}
          onChange={(e) => setJsonText(e.target.value)}
          onBlur={() => jsonText && handleValidate(jsonText)}
        />
      ) : (
        <input
          type="file"
          accept=".json"
          onChange={handleFileChange}
          className="text-sm"
        />
      )}

      {parseError && <p className="text-sm text-red-600">{parseError}</p>}

      {validationErrors.length > 0 && (
        <ul className="text-sm text-red-600 list-disc list-inside space-y-0.5">
          {validationErrors.map((e, i) => (
            <li key={i}>{e}</li>
          ))}
        </ul>
      )}

      {isValid && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-green-700 font-medium">
            <span>✓</span> Manifest valid
          </div>
          <input
            type="text"
            className="w-full border rounded p-2 text-sm"
            placeholder="Niche hint (optional, e.g. 'VAT reconciliation for UK SMEs')"
            value={nicheHint}
            onChange={(e) => setNicheHint(e.target.value)}
          />
          <button
            onClick={handleStart}
            disabled={isSubmitting}
            className="w-full py-2 bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            {isSubmitting ? "Creating…" : "Start Session"}
          </button>
        </div>
      )}

      {!isValid && !parseError && jsonText && (
        <button
          onClick={() => handleValidate(jsonText)}
          className="text-sm text-blue-600 underline"
        >
          Validate
        </button>
      )}
    </div>
  );
};

export default ManifestUpload;
