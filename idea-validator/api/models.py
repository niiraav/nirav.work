"""Pydantic models for the Idea Validator API.

Mirrors the TypeScript types in webapp/lib/types.ts — both sides validate
against the same shapes so frontend and backend can ship independently.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Manifest sub-models
# ---------------------------------------------------------------------------

class BudgetCeiling(BaseModel):
    monthly_burn: float = Field(description="Monthly burn rate in GBP")
    max_cac: float = Field(description="Max Customer Acquisition Cost in GBP. CAC > £100 auto-kills.")


class KnownCompetitor(BaseModel):
    name: str
    known_weakness: str
    threat_trajectory: Literal["unknown", "static", "growing", "declining"]


class RuledOutNiche(BaseModel):
    niche: str
    reason: str
    rejected_by: Literal["skeptic", "human", "system"]


class RequiredEvidence(BaseModel):
    field: str
    resolution: Literal["human", "research", "manifest"]
    blocking: bool
    status: Literal["pending", "resolved"] = "pending"
    value: Optional[Any] = None


class SessionConstraints(BaseModel):
    max_pivots: int = Field(ge=0, le=3, description="How many full restarts the Skeptic can demand")
    max_turns_per_stage: int = Field(ge=3, le=10, description="Debate rounds per stage. Recommended: 4.")
    token_ceiling: int = Field(ge=10000, description="Hard stop if total tokens exceed this")


class ManifestModel(BaseModel):
    lead_segments: Dict[str, int] = Field(description="Verified lead counts per segment")
    technical_constraints: List[str] = Field(description="Hard constraints enforced at every stage")
    budget_ceiling: BudgetCeiling
    timeline_months: int = Field(ge=1, le=36, description="Months until launch deadline")
    known_competitors: List[KnownCompetitor] = []
    ruled_out_niches: List[RuledOutNiche] = []
    required_evidence: List[RequiredEvidence] = []
    session_constraints: SessionConstraints


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    manifest: ManifestModel
    niche_hint: str = ""


class GateDecision(BaseModel):
    decision: Literal["approve", "refine", "reject"]
    rationale: str = ""
    approved_item: str = ""  # niche / pain point / solution name


class RunRequest(BaseModel):
    stage: int = Field(default=1, ge=1, le=5, description="Stage to start/resume from")


# ---------------------------------------------------------------------------
# Session response models
# ---------------------------------------------------------------------------

class SessionSummary(BaseModel):
    session_id: str
    created_at: str
    current_stage: int
    niche_hint: str
    approved_niche: Optional[str] = None
    approved_pain_point: Optional[str] = None
    approved_solution: Optional[str] = None


class TranscriptEntry(BaseModel):
    role: Literal["Synthesizer", "Skeptic"]
    stage: int
    round: int
    turn_type: Literal["deliberation", "pivot"]
    content: str
    claims: Optional[Dict[str, Any]] = None


class KillCondition(BaseModel):
    id: str
    condition: str
    status: Literal["proposed", "signed_off", "inactive", "triggered", "hit"]
    reason: Optional[str] = None


class MomentumTurn(BaseModel):
    turn: int
    objections_raised: int
    objections_resolved: int
    health: float


class GateData(BaseModel):
    convergence_type: Literal["strong", "partial_top2", "partial_top1", "disputed", "diverging", "unknown"]
    kill_conditions: List[KillCondition] = []
    unverified_claims: List[Dict[str, str]] = []
    momentum_summary: List[MomentumTurn] = []
    # Stage-specific fields
    synthesizer_ranking: Optional[List[str]] = None   # Stage 1
    pain_points: Optional[List[Any]] = None              # Stage 2
    solutions: Optional[List[Any]] = None               # Stage 3
    pricing_tiers: Optional[List[Any]] = None            # Stage 4
    unit_economics: Optional[Dict[str, Any]] = None       # Stage 4
    experiments: Optional[List[Any]] = None               # Stage 5


class SessionState(SessionSummary):
    manifest: ManifestModel
    pivot_count: int = 0
    pivot_used: bool = False
    kill_conditions: List[KillCondition] = []
    transcript: List[TranscriptEntry] = []
    approved_business_model: Optional[Dict[str, Any]] = None
    approved_sprint: Optional[Dict[str, Any]] = None
    stages: Dict[str, Any] = {}
    token_usage: List[Dict[str, Any]] = []



# ---------------------------------------------------------------------------
# WebSocket messages (discriminated union)
# ---------------------------------------------------------------------------

class LogMessage(BaseModel):
    type: Literal["log"]
    text: str


class TranscriptMessage(BaseModel):
    type: Literal["transcript"]
    entry: TranscriptEntry


class GateMessage(BaseModel):
    type: Literal["gate"]
    stage: int
    gate_data: GateData


class DoneMessage(BaseModel):
    type: Literal["done"]
    session_id: str


class ErrorMessage(BaseModel):
    type: Literal["error"]
    message: str


WsMessage = Union[LogMessage, TranscriptMessage, GateMessage, DoneMessage, ErrorMessage]
