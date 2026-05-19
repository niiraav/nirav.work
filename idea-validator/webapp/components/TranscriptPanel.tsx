"use client";

import { useEffect, useRef, type FC } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { TranscriptEntry } from "../lib/types";

interface Props {
  entries: TranscriptEntry[];
  isRunning: boolean;
}

// Group entries by round number
function groupByRound(entries: TranscriptEntry[]): Map<number, { synth?: TranscriptEntry; skeptic?: TranscriptEntry }> {
  const map = new Map<number, { synth?: TranscriptEntry; skeptic?: TranscriptEntry }>();
  for (const e of entries) {
    const group = map.get(e.round) ?? {};
    if (e.role === "Synthesizer") group.synth = e;
    else group.skeptic = e;
    map.set(e.round, group);
  }
  return map;
}

// Detect SURVIVE / WEAK / KILL verdict tokens in Skeptic responses
function extractVerdict(text: string): "SURVIVE" | "WEAK" | "KILL" | null {
  if (/\bKILL\b/.test(text)) return "KILL";
  if (/\bWEAK\b/.test(text)) return "WEAK";
  if (/\bSURVIVE\b/.test(text)) return "SURVIVE";
  return null;
}

const VERDICT_COLORS = {
  SURVIVE: "bg-green-100 text-green-800",
  WEAK:    "bg-amber-100 text-amber-800",
  KILL:    "bg-red-100 text-red-800",
};

const TranscriptPanel: FC<Props> = ({ entries, isRunning }) => {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length]);

  const rounds = groupByRound(entries);
  const roundNums = Array.from(rounds.keys()).sort((a, b) => a - b);

  if (roundNums.length === 0 && !isRunning) {
    return (
      <div className="p-6 text-sm text-gray-400 text-center">
        No transcript yet — start the pipeline to begin deliberation.
      </div>
    );
  }

  return (
    <div className="overflow-y-auto max-h-[60vh] p-4 space-y-6">
      {roundNums.map((round) => {
        const { synth, skeptic } = rounds.get(round)!;
        const verdict = skeptic ? extractVerdict(skeptic.content) : null;

        return (
          <div key={round}>
            <div className="text-xs text-gray-400 mb-2 font-semibold tracking-wide uppercase">
              ── Round {round} ──
            </div>
            <div className="grid grid-cols-2 gap-4">
              {/* Synthesizer */}
              <div className="bg-blue-50 rounded-lg p-3">
                <div className="text-xs font-bold text-blue-700 mb-1">SYNTHESIZER</div>
                {synth ? (
                  <div className="prose prose-sm max-w-none text-gray-800">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{synth.content}</ReactMarkdown>
                  </div>
                ) : (
                  isRunning && (
                    <div className="flex items-center gap-1 text-xs text-blue-400">
                      <span className="animate-spin">⟳</span> thinking…
                    </div>
                  )
                )}
              </div>

              {/* Skeptic */}
              <div className="bg-red-50 rounded-lg p-3">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-bold text-red-700">SKEPTIC</span>
                  {verdict && (
                    <span className={`text-xs px-1.5 py-0.5 rounded font-bold ${VERDICT_COLORS[verdict]}`}>
                      {verdict}
                    </span>
                  )}
                </div>
                {skeptic ? (
                  <div className="prose prose-sm max-w-none text-gray-800">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{skeptic.content}</ReactMarkdown>
                  </div>
                ) : (
                  isRunning && (
                    <div className="flex items-center gap-1 text-xs text-red-400">
                      <span className="animate-spin">⟳</span> thinking…
                    </div>
                  )
                )}
              </div>
            </div>
          </div>
        );
      })}

      {isRunning && roundNums.length === 0 && (
        <div className="text-center text-sm text-gray-400 animate-pulse">Pipeline starting…</div>
      )}

      <div ref={bottomRef} />
    </div>
  );
};

export default TranscriptPanel;
