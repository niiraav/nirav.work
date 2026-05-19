import type { FC } from "react";

type Status = "idle" | "running" | "gate" | "done" | "error";

const STAGE_NAMES: Record<number, string> = {
  1: "Niche Alignment",
  2: "Pain Point Research",
  3: "Solution Design",
  4: "Business Model",
  5: "Validation Sprint",
};

const STATUS_BADGE: Record<Status, string> = {
  idle:    "bg-gray-100 text-gray-500",
  running: "bg-blue-100 text-blue-700 animate-pulse",
  gate:    "bg-amber-100 text-amber-700",
  done:    "bg-green-100 text-green-700",
  error:   "bg-red-100 text-red-700",
};

interface Props {
  currentStage: number;
  status: Status;
}

const StageProgress: FC<Props> = ({ currentStage, status }) => {
  const stageName = STAGE_NAMES[currentStage] ?? "Unknown";

  return (
    <div className="flex items-center gap-3 p-4 border-b">
      <div className="flex gap-1.5">
        {[1, 2, 3, 4, 5].map((n) => (
          <div
            key={n}
            className={`w-3 h-3 rounded-full ${
              n <= currentStage ? "bg-blue-600" : "bg-gray-200"
            }`}
          />
        ))}
      </div>
      <span className="text-sm font-medium text-gray-700">
        Stage {currentStage}: {stageName}
      </span>
      <span className={`ml-auto text-xs font-semibold px-2 py-0.5 rounded-full ${STATUS_BADGE[status]}`}>
        {status.toUpperCase()}
      </span>
    </div>
  );
};

export default StageProgress;
