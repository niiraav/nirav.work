// webapp/lib/types.ts
// Mirrors api/models.py — both sides validate against the same shapes.

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

export type Decision = "approve" | "refine" | "reject";
export type ConvergenceType = "strong" | "partial_top2" | "partial_top1" | "disputed" | "diverging" | "unknown";
export type KillStatus = "proposed" | "signed_off" | "inactive" | "triggered" | "hit";
export type Role = "Synthesizer" | "Skeptic";
export type TurnType = "deliberation" | "pivot";

// ---------------------------------------------------------------------------
// Manifest
// ---------------------------------------------------------------------------

export interface BudgetCeiling {
  monthly_burn: number;
  max_cac: number;
}

export interface KnownCompetitor {
  name: string;
  known_weakness: string;
  threat_trajectory: "unknown" | "static" | "growing" | "declining";
}

export interface RuledOutNiche {
  niche: string;
  reason: string;
  rejected_by: "skeptic" | "human" | "system";
}

export interface RequiredEvidence {
  field: string;
  resolution: "human" | "research" | "manifest";
  blocking: boolean;
  status?: "pending" | "resolved";
  value?: unknown;
}

export interface SessionConstraints {
  max_pivots: number;
  max_turns_per_stage: number;
  token_ceiling: number;
}

export interface Manifest {
  lead_segments: Record<string, number>;
  technical_constraints: string[];
  budget_ceiling: BudgetCeiling;
  timeline_months: number;
  known_competitors: KnownCompetitor[];
  ruled_out_niches: RuledOutNiche[];
  required_evidence: RequiredEvidence[];
  session_constraints: SessionConstraints;
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export interface TranscriptEntry {
  role: Role;
  stage: number;
  round: number;
  turn_type: TurnType;
  content: string;
  claims?: Record<string, unknown>;
}

export interface KillCondition {
  id: string;
  condition: string;
  status: KillStatus;
  reason?: string;
}

export interface MomentumTurn {
  turn: number;
  objections_raised: number;
  objections_resolved: number;
  health: number;
}

export interface GateData {
  convergence_type: ConvergenceType;
  kill_conditions: KillCondition[];
  unverified_claims: { claim: string; source: string }[];
  momentum_summary: MomentumTurn[];
  // Stage-specific optional fields
  synthesizer_ranking?: string[]; // Stage 1
  pain_points?: unknown[];        // Stage 2
  solutions?: unknown[];           // Stage 3
  pricing_tiers?: unknown[];       // Stage 4
  unit_economics?: Record<string, unknown>; // Stage 4
  experiments?: unknown[];         // Stage 5
}

export interface SessionSummary {
  session_id: string;
  created_at: string;
  current_stage: number;
  niche_hint: string;
  approved_niche: string | null;
  approved_pain_point: string | null;
  approved_solution: string | null;
}

export interface SessionState extends SessionSummary {
  manifest: Manifest;
  pivot_count: number;
  pivot_used: boolean;
  kill_conditions: KillCondition[];
  transcript: TranscriptEntry[];
  approved_business_model: Record<string, unknown> | null;
  approved_sprint: Record<string, unknown> | null;
  stages: Record<string, { status: string; gate_data: GateData }>;
  token_usage: Record<string, unknown>[];
}

// ---------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------

export interface CreateSessionRequest {
  manifest: Manifest;
  niche_hint?: string;
}

export interface GateDecisionRequest {
  decision: Decision;
  rationale?: string;
  approved_item?: string;
}

// ---------------------------------------------------------------------------
// WebSocket messages (discriminated union)
// ---------------------------------------------------------------------------

export interface LogMessage {
  type: "log";
  text: string;
}

export interface TranscriptMessage {
  type: "transcript";
  entry: TranscriptEntry;
}

export interface GateMessage {
  type: "gate";
  stage: number;
  gate_data: GateData;
}

export interface DoneMessage {
  type: "done";
  session_id: string;
}

export interface ErrorMessage {
  type: "error";
  message: string;
}

export type WsMessage = LogMessage | TranscriptMessage | GateMessage | DoneMessage | ErrorMessage;
