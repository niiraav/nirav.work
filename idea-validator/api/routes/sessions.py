"""REST routes for session CRUD and pipeline control."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.models import (
    CreateSessionRequest,
    GateDecision,
    ManifestModel,
    RunRequest,
)
from api.runner import PipelineRunner, runner as _default_runner

router = APIRouter()


def get_runner() -> PipelineRunner:
    return _default_runner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "session_id": raw.get("session_id", "unknown"),
        "created_at": raw.get("created_at", ""),
        "current_stage": raw.get("current_stage", 1),
        "niche_hint": raw.get("niche_hint", ""),
        "approved_niche": raw.get("approved_niche"),
        "approved_pain_point": raw.get("approved_pain_point"),
        "approved_solution": raw.get("approved_solution"),
    }


# ---------------------------------------------------------------------------
# Routes — note: /sessions/validate-manifest must appear before /{session_id}
# ---------------------------------------------------------------------------

@router.post("/sessions/validate-manifest")
def validate_manifest(manifest: ManifestModel) -> Dict[str, Any]:
    """Validate a manifest JSON without creating a session."""
    return {"valid": True, "errors": []}


@router.post("/sessions", status_code=201)
def create_session(req: CreateSessionRequest) -> Dict[str, Any]:
    """Create a new session from a manifest using the orchestrator."""
    from orchestrator import create_session as _create, save_session
    session = _create(req.manifest.model_dump(), req.niche_hint)
    save_session(session)
    return _to_summary(session)


@router.get("/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions (summary only)."""
    from config import SESSIONS_DIR
    summaries = []
    sessions_path = Path(SESSIONS_DIR)
    if not sessions_path.exists():
        return summaries
    for f in sorted(sessions_path.glob("session_*.json"), reverse=True):
        if "-report" in f.stem:
            continue
        try:
            raw = json.loads(f.read_text())
            summaries.append(_to_summary(raw))
        except Exception:
            pass
    return summaries


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    """Full session state."""
    from orchestrator import load_session
    try:
        session = load_session(session_id)
        session["transcript"] = list(session.get("transcript", []))
        return session
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    """Delete a session file."""
    from config import SESSIONS_DIR
    path = Path(SESSIONS_DIR) / f"{session_id}.json"
    if path.exists():
        path.unlink()
    return None


@router.post("/sessions/{session_id}/run", status_code=202)
def run_session(
    session_id: str,
    body: RunRequest,
    pipeline: PipelineRunner = Depends(get_runner),
) -> Dict[str, Any]:
    """Start or resume pipeline for a session."""
    from orchestrator import load_session
    try:
        load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if pipeline.is_running(session_id):
        raise HTTPException(status_code=409, detail="Pipeline already running for this session")
    pipeline.start_pipeline(session_id, body.stage)
    return {"status": "started", "session_id": session_id, "stage": body.stage}


@router.post("/sessions/{session_id}/gate/{stage}")
def submit_gate(
    session_id: str,
    stage: int,
    req: GateDecision,
    pipeline: PipelineRunner = Depends(get_runner),
) -> Dict[str, Any]:
    """Submit a human gate decision."""
    try:
        pipeline.submit_gate(session_id, {
            "decision": req.decision,
            "rationale": req.rationale,
            "approved_item": req.approved_item,
            "timestamp": datetime.utcnow().isoformat(),
        })
    except KeyError:
        raise HTTPException(status_code=409, detail="No gate is waiting for a decision")
    return {"status": "ok"}


@router.get("/sessions/{session_id}/report")
def get_report(session_id: str) -> Dict[str, str]:
    """Return the final validation report markdown (if generated)."""
    from config import SESSIONS_DIR
    path = Path(SESSIONS_DIR) / f"{session_id}-report.md"
    if path.exists():
        return {"markdown": path.read_text()}
    raise HTTPException(status_code=404, detail="Report not yet generated")
