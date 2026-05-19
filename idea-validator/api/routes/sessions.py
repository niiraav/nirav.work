"""REST routes for session CRUD and pipeline control.

All routes return valid stub responses — real logic wired in Week 3.
"""

import json
import os
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from api.models import (
    CreateSessionRequest,
    GateDecision,
    ManifestModel,
    SessionState,
    SessionSummary,
)
from api.runner import runner

router = APIRouter()

SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sessions")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _list_session_files() -> List[str]:
    """Return sorted list of session JSON filenames."""
    if not os.path.isdir(SESSIONS_DIR):
        return []
    files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json") and f.startswith("session_")]
    return sorted(files)


def _load_session(session_id: str) -> Dict[str, Any]:
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    with open(path) as f:
        return json.load(f)


def _to_summary(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Strip full session down to summary fields."""
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
# Routes
# ---------------------------------------------------------------------------

@router.post("/sessions", status_code=201)
def create_session(req: CreateSessionRequest) -> Dict[str, Any]:
    """Create a new session from a manifest."""
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    session = {
        "session_id": session_id,
        "manifest": req.manifest.model_dump(),
        "niche_hint": req.niche_hint,
        "created_at": datetime.now().isoformat(),
        "current_stage": 1,
        "pivot_count": 0,
        "pivot_used": False,
        "kill_conditions": [],
        "stages": {},
        "transcript": [],
        "token_usage": [],
    }
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    with open(os.path.join(SESSIONS_DIR, f"{session_id}.json"), "w") as f:
        json.dump(session, f, indent=2)
    return _to_summary(session)


@router.get("/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions (summary only)."""
    return [_to_summary(_load_session(f.replace(".json", ""))) for f in _list_session_files()]


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    """Full session state."""
    return _load_session(session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: str) -> None:
    """Delete a session file."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if os.path.exists(path):
        os.remove(path)
    return None


@router.post("/sessions/{session_id}/run")
def run_session(session_id: str) -> Dict[str, str]:
    """Start or resume pipeline for a session."""
    # Validate session exists
    _load_session(session_id)
    # Stub — Week 3: runner.start_session(session_id, manifest, niche_hint)
    return {"status": "started", "session_id": session_id}


@router.post("/sessions/{session_id}/gate/{stage}")
def submit_gate(session_id: str, stage: int, req: GateDecision) -> Dict[str, Any]:
    """Submit a human gate decision."""
    # Validate session exists
    _load_session(session_id)
    # Stub — Week 3: runner.submit_gate(session_id, stage, req.model_dump())
    return {"status": "ok", "decision": req.decision, "stage": stage}


@router.get("/sessions/{session_id}/report")
def get_report(session_id: str) -> Dict[str, str]:
    """Return the final validation report markdown (if generated)."""
    report_path = os.path.join(SESSIONS_DIR, f"{session_id}-report.md")
    if os.path.exists(report_path):
        with open(report_path) as f:
            return {"markdown": f.read()}
    # Fallback: check if session has a report field
    session = _load_session(session_id)
    if "report" in session:
        return {"markdown": session["report"]}
    raise HTTPException(status_code=404, detail="Report not yet generated")


@router.post("/sessions/validate-manifest")
def validate_manifest(manifest: ManifestModel) -> Dict[str, Any]:
    """Validate a manifest JSON without creating a session."""
    # Pydantic already validated the shape; any logic checks go here
    return {"valid": True, "errors": []}
