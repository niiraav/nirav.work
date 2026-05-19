"""Pipeline runner interface — stubs only for Week 2.

Real implementation (pipeline thread, gate queue, stdout → WebSocket)
will be wired in Week 3.  For now every method raises NotImplementedError.
"""

from typing import Any, Callable, Dict, Optional
from api.models import GateData


class PipelineRunner:
    """Manages a background deliberation thread and streams output."""

    def __init__(self):
        self._active_session_id: Optional[str] = None
        self._gate_queue: Optional[Any] = None  # queue.Queue[GateDecision]
        self._ws_clients: Dict[str, Any] = {}   # session_id → list of WebSocket connections

    # -------------------------------------------------------------------
    # Public interface (called by REST routes)
    # -------------------------------------------------------------------

    def start_session(self, session_id: str, manifest: Dict[str, Any], niche_hint: str = "") -> None:
        """Kick off Stage 1 in a background thread."""
        raise NotImplementedError("Wired in Week 3")

    def resume_session(self, session_id: str, stage: int) -> None:
        """Resume an existing session at the given stage."""
        raise NotImplementedError("Wired in Week 3")

    def submit_gate(self, session_id: str, stage: int, decision: Dict[str, Any]) -> None:
        """Put a gate decision into the queue, unblocking the pipeline thread."""
        raise NotImplementedError("Wired in Week 3")

    def register_ws(self, session_id: str, ws: Any) -> None:
        """Add a WebSocket connection for a session."""
        raise NotImplementedError("Wired in Week 3")

    def unregister_ws(self, session_id: str, ws: Any) -> None:
        """Remove a WebSocket connection."""
        raise NotImplementedError("Wired in Week 3")

    # -------------------------------------------------------------------
    # Internal (called by the pipeline thread)
    # -------------------------------------------------------------------

    def _send_log(self, session_id: str, text: str) -> None:
        raise NotImplementedError("Wired in Week 3")

    def _send_transcript(self, session_id: str, entry: Dict[str, Any]) -> None:
        raise NotImplementedError("Wired in Week 3")

    def _send_gate(self, session_id: str, stage: int, gate_data: GateData) -> None:
        raise NotImplementedError("Wired in Week 3")

    def _send_done(self, session_id: str) -> None:
        raise NotImplementedError("Wired in Week 3")

    def _send_error(self, session_id: str, message: str) -> None:
        raise NotImplementedError("Wired in Week 3")

    def _gate_callback(self, stage: int, gate_data: Dict[str, Any]) -> Dict[str, Any]:
        """Called by the pipeline thread when a gate is reached.
        Blocks on the queue until a decision arrives via HTTP POST."""
        raise NotImplementedError("Wired in Week 3")


# Singleton — imported by routes
runner = PipelineRunner()
