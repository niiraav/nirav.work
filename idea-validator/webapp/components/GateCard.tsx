"use client";

import { useState, type FC } from "react";
import type { GateData, GateDecisionRequest } from "../lib/types";
import KillConditionBadge from "./KillConditionBadge";
import MomentumBar from "./MomentumBar";

const STAGE_NAMES: Record<number, string> = {
  1: "Niche Alignment",
  2: "Pain Point Research",
  3: "Solution Design",
  4: "Business Model",
  5: "Validation Sprint",
};

interface Props {
  stage: number;
  gateData: GateData;
  onDecide: (d: GateDecisionRequest) => void;
}

function getItems(stage: number, gateData: GateData): string[] {
  if (stage === 1) return (gateData.synthesizer_ranking ?? []) as string[];
  if (stage === 2) return ((gateData.pain_points ?? []) as any[]).map((p) => p.name ?? String(p));
  if (stage === 3) return ((gateData.solutions ?? []) as any[]).map((s) => s.name ?? String(s));
  return [];
}

const GateCard: FC<Props> = ({ stage, gateData, onDecide }) => {
  const items = getItems(stage, gateData);
  const [selectedItem, setSelectedItem] = useState(items[0] ?? "");
  const [rationale, setRationale] = useState("");
  const [killsExpanded, setKillsExpanded] = useState(false);
  const [claimsExpanded, setClaimsExpanded] = useState(false);

  const convergenceColor =
    gateData.convergence_type === "strong"
      ? "text-green-700"
      : ["partial_top2", "partial_top1"].includes(gateData.convergence_type)
      ? "text-amber-700"
      : "text-red-700";

  const activeKills = gateData.kill_conditions.filter((k) =>
    ["proposed", "signed_off"].includes(k.status)
  );
  const inactiveKills = gateData.kill_conditions.filter((k) =>
    ["inactive", "triggered", "hit"].includes(k.status)
  );

  function handleDecide(decision: "approve" | "refine" | "reject") {
    onDecide({ decision, rationale, approved_item: selectedItem });
  }

  return (
    <div className="border-2 border-amber-400 rounded-xl p-5 bg-amber-50 space-y-4 mx-4 my-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-bold">
          GATE — Stage {stage}: {STAGE_NAMES[stage]}
        </h2>
        <span className={`text-sm font-semibold ${convergenceColor}`}>
          convergence: [{gateData.convergence_type.replace(/_/g, " ")}]
        </span>
      </div>

      {/* Item selector (stages 1–3) */}
      {items.length > 0 && (
        <div className="space-y-1">
          <div className="text-sm font-semibold text-gray-700 mb-1">
            {stage === 1 ? "Niches" : stage === 2 ? "Pain Points" : "Solutions"}
          </div>
          {items.map((item) => (
            <label key={item} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="gate-item"
                value={item}
                checked={selectedItem === item}
                onChange={() => setSelectedItem(item)}
              />
              <span className="text-sm">{item}</span>
            </label>
          ))}
        </div>
      )}

      {/* Stage 4 — pricing summary */}
      {stage === 4 && gateData.pricing_tiers && (
        <div className="text-sm space-y-1">
          <div className="font-semibold text-gray-700">Pricing Tiers</div>
          {(gateData.pricing_tiers as any[]).map((tier, i) => (
            <div key={i} className="text-gray-600">
              {tier.name ?? `Tier ${i + 1}`}: {tier.price ?? "—"}
            </div>
          ))}
        </div>
      )}

      {/* Stage 5 — experiments */}
      {stage === 5 && gateData.experiments && (
        <div className="text-sm space-y-1">
          <div className="font-semibold text-gray-700">Experiments</div>
          {(gateData.experiments as any[]).map((ex, i) => (
            <div key={i} className="text-gray-600">
              {ex.name ?? ex.hypothesis ?? JSON.stringify(ex)}
            </div>
          ))}
        </div>
      )}

      {/* Kill conditions */}
      <div className="text-sm">
        <button
          className="text-gray-600 underline underline-offset-2"
          onClick={() => setKillsExpanded((v) => !v)}
        >
          Kill conditions: {activeKills.length} active · {inactiveKills.length} inactive{" "}
          [{killsExpanded ? "collapse" : "expand"}]
        </button>
        {killsExpanded && (
          <div className="mt-2 flex flex-wrap gap-1">
            {gateData.kill_conditions.map((kc) => (
              <KillConditionBadge key={kc.id} condition={kc} />
            ))}
          </div>
        )}
      </div>

      {/* Unverified claims */}
      {gateData.unverified_claims.length > 0 && (
        <div className="text-sm">
          <button
            className="text-gray-600 underline underline-offset-2"
            onClick={() => setClaimsExpanded((v) => !v)}
          >
            Unverified claims: {gateData.unverified_claims.length} flagged{" "}
            [{claimsExpanded ? "collapse" : "expand"}]
          </button>
          {claimsExpanded && (
            <ul className="mt-2 list-disc list-inside text-gray-600 space-y-0.5">
              {gateData.unverified_claims.map((c, i) => (
                <li key={i}>{c.claim}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Momentum */}
      <MomentumBar turns={gateData.momentum_summary} />

      {/* Rationale */}
      <textarea
        className="w-full border rounded p-2 text-sm resize-none"
        rows={2}
        placeholder="Rationale (optional)"
        value={rationale}
        onChange={(e) => setRationale(e.target.value)}
      />

      {/* Decision buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => handleDecide("approve")}
          className="flex-1 py-2 bg-green-600 text-white font-semibold rounded-lg hover:bg-green-700"
        >
          APPROVE
        </button>
        <button
          onClick={() => handleDecide("refine")}
          className="flex-1 py-2 bg-amber-500 text-white font-semibold rounded-lg hover:bg-amber-600"
        >
          REFINE
        </button>
        <button
          onClick={() => handleDecide("reject")}
          className="flex-1 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700"
        >
          REJECT
        </button>
      </div>
    </div>
  );
};

export default GateCard;
