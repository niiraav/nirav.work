"use client";

import { useState, type FC } from "react";
import type { KillCondition } from "../lib/types";

interface Props {
  condition: KillCondition;
}

const STATUS_STYLES: Record<string, string> = {
  signed_off: "bg-green-100 text-green-800 border-green-200",
  inactive:   "bg-gray-100 text-gray-400 border-gray-200 line-through",
  proposed:   "bg-amber-100 text-amber-800 border-amber-200",
  triggered:  "bg-red-100 text-red-800 border-red-200",
  hit:        "bg-red-200 text-red-900 border-red-300 font-bold",
};

const KillConditionBadge: FC<Props> = ({ condition }) => {
  const [expanded, setExpanded] = useState(false);
  const text = condition.condition;
  const truncated = text.length > 80 ? text.slice(0, 80) + "…" : text;
  const style = STATUS_STYLES[condition.status] ?? STATUS_STYLES.proposed;

  return (
    <span
      className={`inline-block text-xs px-2 py-0.5 border rounded cursor-pointer select-none ${style}`}
      onClick={() => setExpanded((v) => !v)}
      title={condition.status}
    >
      {expanded ? text : truncated}
    </span>
  );
};

export default KillConditionBadge;
