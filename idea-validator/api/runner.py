"""Pipeline runner — real implementation for Week 3.

Runs the deliberation pipeline in a background thread, streams output via
WebSocket, and blocks on gate decisions sent from the frontend via HTTP POST.
"""

import asyncio
import os
import queue
import sys
import threading
from typing import Any, Dict, List, Optional

from fastapi import WebSocket


# ---------------------------------------------------------------------------
# Helper: stdout capture (redirected per-thread)
# ---------------------------------------------------------------------------

class _StdoutCapture:
    def __init__(self, send_fn, real_stdout):
        self._send = send_fn
        self._real = real_stdout

    def write(self, text: str):
        if text.strip():
            self._send({"type": "log", "text": text.rstrip()})
        self._real.write(text)

    def flush(self):
        self._real.flush()


# ---------------------------------------------------------------------------
# Helper: transcript list that broadcasts on every append
# ---------------------------------------------------------------------------

class _TranscriptList(list):
    def __init__(self, callback, initial=()):
        super().__init__(initial)
        self._cb = callback

    def append(self, entry):
        super().append(entry)
        self._cb(entry)


# ---------------------------------------------------------------------------
# Gate decision helper (mirrors main.py _handle_gate approve logic)
# ---------------------------------------------------------------------------

def _apply_gate_decision(session: dict, stage_num: int, decision: dict, gate_data: dict):
    if decision["decision"] != "approve":
        return
    item = decision.get("approved_item", "")

    if stage_num == 1:
        niche = item or (gate_data.get("synthesizer_ranking") or [""])[0]
        session["approved_niche"] = niche
        session["current_stage"] = 2

    elif stage_num == 2:
        pps = gate_data.get("pain_points", [])
        pp = item or (pps[0].get("name", "") if pps else "")
        session["approved_pain_point"] = pp
        session["current_stage"] = 3

    elif stage_num == 3:
        sols = gate_data.get("solutions", [])
        sol = item or (sols[0].get("name", "") if sols else "")
        session["approved_solution"] = sol
        session["current_stage"] = 4

    elif stage_num == 4:
        session["approved_business_model"] = {
            "pricing_tiers": gate_data.get("pricing_tiers", []),
            "unit_economics": gate_data.get("unit_economics", {}),
            "cac_tier": gate_data.get("cac_tier"),
            "cac_kill_triggered": gate_data.get("cac_kill_triggered", False),
        }
        session["current_stage"] = 5

    elif stage_num == 5:
        session["approved_sprint"] = {
            "experiments": gate_data.get("experiments", []),
            "sprint_duration_days": gate_data.get("sprint_duration_days", 30),
        }
        session["current_stage"] = 6


# ---------------------------------------------------------------------------
# PipelineRunner
# ---------------------------------------------------------------------------

class PipelineRunner:
    def __init__(self):
        self._threads: Dict[str, threading.Thread] = {}
        self._gate_queues: Dict[str, queue.Queue] = {}
        self._ws_clients: Dict[str, List[WebSocket]] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    # ── WebSocket management ─────────────────────────────────────────────────

    async def register_ws(self, session_id: str, ws: WebSocket):
        self._ws_clients.setdefault(session_id, []).append(ws)

    async def unregister_ws(self, session_id: str, ws: WebSocket):
        clients = self._ws_clients.get(session_id, [])
        if ws in clients:
            clients.remove(ws)

    async def _broadcast(self, session_id: str, message: dict):
        for ws in self._ws_clients.get(session_id, [])[:]:
            try:
                await ws.send_json(message)
            except Exception:
                clients = self._ws_clients.get(session_id, [])
                if ws in clients:
                    clients.remove(ws)

    def _send_from_thread(self, session_id: str, message: dict):
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._broadcast(session_id, message), self._loop
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def start_pipeline(self, session_id: str, stage: int = 1):
        if session_id in self._threads and self._threads[session_id].is_alive():
            return
        self._gate_queues[session_id] = queue.Queue()
        t = threading.Thread(
            target=self._run_pipeline,
            args=(session_id, stage),
            daemon=True,
        )
        self._threads[session_id] = t
        t.start()

    def submit_gate(self, session_id: str, decision: dict):
        if session_id not in self._gate_queues:
            raise KeyError(f"No active pipeline for session {session_id}")
        self._gate_queues[session_id].put(decision)

    def is_running(self, session_id: str) -> bool:
        t = self._threads.get(session_id)
        return t is not None and t.is_alive()

    # ── Pipeline thread ──────────────────────────────────────────────────────

    def _run_pipeline(self, session_id: str, start_stage: int):
        real_stdout = sys.stdout
        sys.stdout = _StdoutCapture(
            lambda msg: self._send_from_thread(session_id, msg),
            real_stdout,
        )
        try:
            self._execute(session_id, start_stage)
        except Exception as e:
            self._send_from_thread(session_id, {"type": "error", "message": str(e)})
        finally:
            sys.stdout = real_stdout

    def _execute(self, session_id: str, start_stage: int):
        from orchestrator import (
            load_session, save_session,
            run_stage1, run_stage2, run_stage3, run_stage4, run_stage5,
            generate_final_report,
        )
        from agents import Synthesizer, Skeptic
        from gate_manager import GateManager
        from config import SESSIONS_DIR

        session = load_session(session_id)

        # Intercept transcript for real-time streaming
        session["transcript"] = _TranscriptList(
            lambda entry: self._send_from_thread(session_id, {"type": "transcript", "entry": entry}),
            session.get("transcript", []),
        )

        synthesizer = Synthesizer()
        skeptic = Skeptic()

        # Restore agent histories when resuming
        history_key = f"agent_histories_stage{start_stage - 1}" if start_stage > 1 else "agent_histories"
        histories = session.get(history_key, session.get("agent_histories", {}))
        if histories.get("synthesizer"):
            synthesizer.restore(histories["synthesizer"])
        if histories.get("skeptic"):
            skeptic.restore(histories["skeptic"])
            skeptic.pivot_used = session.get("pivot_used", False)

        gate_manager = GateManager()
        stage_fns = {
            1: run_stage1, 2: run_stage2, 3: run_stage3,
            4: run_stage4, 5: run_stage5,
        }

        for stage_num in range(start_stage, 6):
            result = stage_fns[stage_num](session, synthesizer, skeptic)
            session["stages"][str(stage_num)] = result
            save_session(session)

            gate_decision = gate_manager.run_gate(
                stage_num=stage_num,
                session_id=session_id,
                gate_data=result["gate_data"],
                gate_callback=lambda s, d, _sn=stage_num: self._gate_callback(session_id, _sn, d),
            )

            if gate_decision["decision"] == "reject":
                self._send_from_thread(
                    session_id, {"type": "error", "message": f"Stage {stage_num} rejected by user."}
                )
                return

            _apply_gate_decision(session, stage_num, gate_decision, result["gate_data"])
            save_session(session)

        report = generate_final_report(session)
        report_path = os.path.join(SESSIONS_DIR, f"{session_id}-report.md")
        with open(report_path, "w") as f:
            f.write(report)

        self._send_from_thread(session_id, {"type": "done", "session_id": session_id})

    def _gate_callback(self, session_id: str, stage_num: int, gate_data: dict) -> dict:
        self._send_from_thread(session_id, {"type": "gate", "stage": stage_num, "gate_data": gate_data})
        return self._gate_queues[session_id].get(timeout=3600)


# Singleton — imported by routes and main.py
runner = PipelineRunner()
