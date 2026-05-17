import json
import sys
from agents import ClaudeAgent, KimiAgent, STAGE_NAMES
from tools import run_stage_searches, format_lead_counts
from output import write_final, write_escalation
from config import MAX_ROUNDS_PER_STAGE, CONFIDENCE_THRESHOLD

STAGES_NEEDING_SEARCH = {2, 4}


def _format_transcript(transcript: list[dict], stage_num: int = None) -> str:
    """Format transcript for injection into agent prompts."""
    entries = [e for e in transcript if stage_num is None or e["stage"] == stage_num]
    if not entries:
        return "_No prior discussion._"
    lines = []
    for e in entries:
        lines.append(f"--- [{e['role']} | Stage {e['stage']} Round {e['round']}] ---\n{e['content']}")
    return "\n\n".join(lines)


def _append(transcript: list, role: str, stage: int, round_num: int, content: str):
    transcript.append({"role": role, "stage": stage, "round": round_num, "content": content})


def run_stage(stage_num: int, session: dict, claude: ClaudeAgent, kimi: KimiAgent) -> dict:
    """Run one stage's discussion loop. Returns convergence result dict."""
    niche = session["niche"]
    transcript = session["transcript"]
    print(f"\n{'='*60}")
    print(f"  STAGE {stage_num}: {STAGE_NAMES[stage_num]}")
    print(f"{'='*60}")

    # Inject lead base context for Stage 1 search context
    if stage_num == 1:
        lead_context = format_lead_counts()
        _append(transcript, "System", stage_num, 0, f"Lead base context:\n{lead_context}")

    for round_num in range(1, MAX_ROUNDS_PER_STAGE + 1):
        print(f"\n  Round {round_num}/{MAX_ROUNDS_PER_STAGE}")

        # Research phase: run searches for stages that need them
        search_results = ""
        if stage_num in STAGES_NEEDING_SEARCH:
            print("  [Kimi] Running multi-platform searches...")
            search_results = run_stage_searches(niche)

        # Kimi's turn
        print("  [Kimi] Researching and synthesising...")
        stage_transcript = _format_transcript(transcript, stage_num)
        kimi_output = kimi.turn(stage_num, search_results, stage_transcript)
        _append(transcript, "Kimi", stage_num, round_num, kimi_output)
        print(f"\n--- KIMI ---\n{kimi_output}\n")

        # Claude's turn
        print("  [Claude] Reviewing and directing...")
        stage_transcript = _format_transcript(transcript, stage_num)
        claude_output = claude.turn(stage_num, stage_transcript)
        _append(transcript, "Claude", stage_num, round_num, claude_output)
        print(f"\n--- CLAUDE ---\n{claude_output}\n")

        # Convergence check
        print("  [Convergence check...]")
        stage_transcript = _format_transcript(transcript, stage_num)
        try:
            decision = claude.decide_convergence(stage_num, stage_transcript)
        except (json.JSONDecodeError, Exception) as e:
            print(f"  Warning: convergence check failed ({e}), continuing round.")
            decision = {"confidence": 50, "action": "continue", "confirmed_points": [], "disputed_points": [], "reasoning": "parse error"}

        confidence = decision.get("confidence", 0)
        action = decision.get("action", "continue")
        print(f"  Confidence: {confidence}% → {action.upper()}")

        # Store stage result
        session.setdefault("stages", {}).setdefault(str(stage_num), {
            "status": "in_progress", "confirmed_points": [], "disputed_points": [], "rounds": []
        })
        stage_data = session["stages"][str(stage_num)]
        stage_data["rounds"].append({
            "round": round_num,
            "confidence": confidence,
            "action": action,
            "confirmed_points": decision.get("confirmed_points", []),
            "disputed_points": decision.get("disputed_points", []),
        })
        # Accumulate confirmed/disputed across rounds
        for p in decision.get("confirmed_points", []):
            if p not in stage_data["confirmed_points"]:
                stage_data["confirmed_points"].append(p)
        for p in decision.get("disputed_points", []):
            if p not in stage_data["disputed_points"]:
                stage_data["disputed_points"].append(p)

        if action == "advance":
            stage_data["status"] = "completed"
            stage_data["confidence"] = confidence
            return decision
        elif action == "escalate":
            stage_data["status"] = "escalated"
            stage_data["confidence"] = confidence
            return decision

    # Max rounds hit without convergence → escalate
    decision = {
        "confidence": 35,
        "action": "escalate",
        "confirmed_points": stage_data.get("confirmed_points", []),
        "disputed_points": stage_data.get("disputed_points", []),
        "reasoning": f"Max rounds ({MAX_ROUNDS_PER_STAGE}) reached without convergence.",
    }
    stage_data["status"] = "escalated"
    return decision


def run_session(session: dict, start_stage: int, end_stage: int = 5):
    claude = ClaudeAgent()
    kimi = KimiAgent()

    for stage_num in range(start_stage, end_stage + 1):
        decision = run_stage(stage_num, session, claude, kimi)
        _save_session(session)

        if decision["action"] == "escalate":
            write_escalation(
                session,
                stage_num,
                reason=decision.get("reasoning", "Escalated"),
                disputed_points=decision.get("disputed_points", []),
            )
            print(f"\nStage {stage_num} needs human review. Session saved — resume with:")
            print(f"  python main.py --resume {session['session_id']} --stage {stage_num}")
            sys.exit(0)

        print(f"\nStage {stage_num} complete. Confidence: {decision['confidence']}%")

    # All stages done
    session["final_confidence"] = _overall_confidence(session)
    _save_session(session)
    write_final(session)
    print(f"\nValidation complete. Overall confidence: {session['final_confidence']}%")


def _overall_confidence(session: dict) -> int:
    stages = session.get("stages", {})
    scores = [s.get("confidence", 0) for s in stages.values() if s.get("status") == "completed"]
    return int(sum(scores) / len(scores)) if scores else 0


def _save_session(session: dict):
    import os
    from config import SESSIONS_DIR
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    path = os.path.join(SESSIONS_DIR, f"{session['session_id']}.json")
    with open(path, "w") as f:
        json.dump(session, f, indent=2)
