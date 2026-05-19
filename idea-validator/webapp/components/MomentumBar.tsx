import type { FC } from "react";
import type { MomentumTurn } from "../lib/types";

interface Props {
  turns: MomentumTurn[];
}

function segmentColor(health: number | null): string {
  if (health === null) return "bg-gray-300";
  if (health > 0.2) return "bg-green-500";
  if (health < -0.2) return "bg-red-500";
  return "bg-amber-400";
}

const MomentumBar: FC<Props> = ({ turns }) => {
  if (!turns || turns.length === 0) return null;

  return (
    <div className="flex items-center gap-1">
      <span className="text-xs text-gray-500 mr-1">Momentum</span>
      {turns.map((t) => (
        <div
          key={t.turn}
          title={`Round ${t.turn}: health ${t.health?.toFixed(2) ?? "n/a"}`}
          className={`h-4 w-5 rounded-sm ${segmentColor(t.health)}`}
        />
      ))}
    </div>
  );
};

export default MomentumBar;
