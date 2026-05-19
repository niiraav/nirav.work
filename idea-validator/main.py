#!/usr/bin/env python3
"""
idea-validator v2: Falsification Engine — Dual-Agent Deliberation

Usage:
  python main.py --manifest manifest.json --niche "MOT Reminder SaaS"
  python main.py --test --manifest manifest.json --niche "MOT Reminder SaaS"
  python main.py --resume session_20260518_132909 --stage 1
  python main.py --resume session_20260518_132909 --stage 1 --non-interactive
  python main.py --list
"""

import argparse
import json
import os
import sys

from config import load_manifest, check_manifest_evidence, get_session_constraints
from orchestrator import (
    create_session, load_session, save_session, list_sessions, run_stage1, run_stage2, run_stage3, run_stage4, run_stage5, generate_final_report
)
from agents import Synthesizer, Skeptic
from gate_manager import GateManager


def _check_env():
    from config import FIREWORKS_API_KEY
    if not FIREWORKS_API_KEY:
        print("Error: FIREWORKS_API_KEY not set. Check .env file.")
        sys.exit(1)


def _handle_gate(result, session, manifest_path, niche_hint, auto_approve=False, stage_num=1, non_interactive=False):
    """Handle the human gate after any stage deliberation."""
    if result["status"] != "gate":
        return

    gate_manager = GateManager()
    decision = gate_manager.run_gate(
        stage_num=stage_num,
        session_id=session["session_id"],
        gate_data=result["gate_data"],
        auto_approve=auto_approve,
        non_interactive=non_interactive,
    )
    print(f"\n🚪 Gate decision: {decision['decision'].upper()}")

    if decision["decision"] == "reject" and decision.get("rationale"):
        manifest = session.get("manifest", load_manifest(manifest_path))
        if stage_num == 1:
            manifest.setdefault("ruled_out_niches", []).append({
                "niche": niche_hint or session["session_id"],
                "reason": decision["rationale"],
                "rejected_by": "human",
            })
            manifest_path = manifest_path or "manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
            print(f"   Rejection rationale saved to manifest.")
        elif stage_num == 2:
            # Stage 2 rejection means go back to Stage 1
            print(f"   Rejection rationale: {decision['rationale']}")
            print("   Returning to Stage 1. Resume with:")
            session["current_stage"] = 1
            if "approved_pain_point" in session:
                del session["approved_pain_point"]
            save_session(session)
            print(f"   python main.py --resume {session['session_id']} --stage 1")
            return
        elif stage_num == 3:
            # Stage 3 rejection means go back to Stage 2
            print(f"   Rejection rationale: {decision['rationale']}")
            print("   Returning to Stage 2. Resume with:")
            session["current_stage"] = 2
            if "approved_solution" in session:
                del session["approved_solution"]
            save_session(session)
            print(f"   python main.py --resume {session['session_id']} --stage 2")
            return
        elif stage_num == 4:
            # Stage 4 rejection means go back to Stage 3
            print(f"   Rejection rationale: {decision['rationale']}")
            print("   Returning to Stage 3. Resume with:")
            session["current_stage"] = 3
            if "approved_business_model" in session:
                del session["approved_business_model"]
            save_session(session)
            print(f"   python main.py --resume {session['session_id']} --stage 3")
            return
        elif stage_num == 5:
            # Stage 5 rejection means go back to Stage 4
            print(f"   Rejection rationale: {decision['rationale']}")
            print("   Returning to Stage 4. Resume with:")
            session["current_stage"] = 4
            if "approved_sprint" in session:
                del session["approved_sprint"]
            save_session(session)
            print(f"   python main.py --resume {session['session_id']} --stage 4")
            return

    if decision["decision"] == "approve":
        gate_data = result.get("gate_data", {})
        if stage_num == 1:
            # Store the approved niche from gate rankings
            synth_ranking = gate_data.get("synthesizer_ranking", [])
            sk_ranking = gate_data.get("skeptic_ranking", [])
            approved = synth_ranking[0] if synth_ranking else (sk_ranking[0] if sk_ranking else "")
            session["approved_niche"] = approved
            session["current_stage"] = 2
            save_session(session)
            print(f"   Approved niche: {approved}")
            print("   Session advanced to Stage 2. Resume with:")
            print(f"   python main.py --resume {session['session_id']} --stage 2")
        elif stage_num == 2:
            # Store the approved pain point
            pain_points = gate_data.get("pain_points", [])
            approved_pp = pain_points[0].get("name", "") if pain_points else ""
            session["approved_pain_point"] = approved_pp
            session["current_stage"] = 3
            save_session(session)
            print(f"   Approved pain point: {approved_pp}")
            print("   Session advanced to Stage 3. Resume with:")
            print(f"   python main.py --resume {session['session_id']} --stage 3")
        elif stage_num == 3:
            # Store the approved solution
            solutions = gate_data.get("solutions", [])
            approved_sol = solutions[0].get("name", "") if solutions else ""
            session["approved_solution"] = approved_sol
            session["current_stage"] = 4
            save_session(session)
            print(f"   Approved solution: {approved_sol}")
            print("   Session advanced to Stage 4. Resume with:")
            print(f"   python main.py --resume {session['session_id']} --stage 4")
        elif stage_num == 4:
            # Store the approved business model
            pricing_tiers = gate_data.get("pricing_tiers", [])
            unit_economics = gate_data.get("unit_economics", {})
            session["approved_business_model"] = {
                "pricing_tiers": pricing_tiers,
                "unit_economics": unit_economics,
                "cac_tier": gate_data.get("cac_tier"),
                "cac_kill_triggered": gate_data.get("cac_kill_triggered", False),
            }
            session["current_stage"] = 5
            save_session(session)
            print(f"   Approved business model")
            if unit_economics.get("cac") is not None:
                print(f"   CAC: £{unit_economics['cac']:.0f} ({unit_economics.get('cac_tier', '?')})")
            print("   Session advanced to Stage 5. Resume with:")
            print(f"   python main.py --resume {session['session_id']} --stage 5")
        elif stage_num == 5:
            # Store the approved sprint plan and generate final report
            experiments = gate_data.get("experiments", [])
            session["approved_sprint"] = {
                "experiments": experiments,
                "sprint_duration_days": gate_data.get("sprint_duration_days", 30),
            }
            session["current_stage"] = 6
            save_session(session)
            print(f"   Approved validation sprint: {len(experiments)} experiments")
            print("   ✅ ALL GATES PASSED — generating final report...")
            
            report = generate_final_report(session)
            report_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "sessions",
                f"{session['session_id']}-report.md"
            )
            with open(report_path, "w") as f:
                f.write(report)
            print(f"\n📄 Final report saved: {report_path}")
            print("\n" + "="*70)
            print("  VALIDATION COMPLETE")
            print("="*70)

    if decision["decision"] == "refine":
        print(f"   Refinement requested: {decision.get('rationale', 'No rationale provided')}")
        print("   Re-run with updated manifest or resume to continue deliberation.")

    if decision["decision"] == "timeout":
        print("   Gate timed out. Session saved. Resume when ready:")
        print(f"   python main.py --resume {session['session_id']} --stage {stage_num}")


def _run_new_session(manifest_path: str, niche_hint: str = "", auto_approve: bool = False, non_interactive: bool = False):
    manifest = load_manifest(manifest_path)

    # Check blocking evidence
    blocking = check_manifest_evidence(manifest)
    if blocking:
        print("\n⛔ BLOCKING evidence required before Stage 1 can start:\n")
        for item in blocking:
            print(f"  - {item['field']} (resolution: {item['resolution']})")
        print("\nPlease resolve these in your manifest and re-run.")
        sys.exit(1)

    session = create_session(manifest, niche_hint)
    synthesizer = Synthesizer()
    skeptic = Skeptic()

    try:
        result = run_stage1(session, synthesizer, skeptic)
        session["stages"]["1"] = result
        session["transcript"] = result.get("transcript", [])
        save_session(session)

        _handle_gate(result, session, manifest_path, niche_hint, auto_approve=auto_approve, non_interactive=non_interactive)

    except KeyboardInterrupt:
        print("\n\nInterrupted. Saving session...")
        save_session(session)
        sys.exit(0)


def _run_resume(session_id: str, stage_num: int, auto_approve: bool = False, non_interactive: bool = False):
    session = load_session(session_id)
    manifest = session.get("manifest", {})
    constraints = get_session_constraints(manifest)

    print(f"\nResuming session: {session_id}")
    print(f"  Stage: {stage_num}")
    print(f"  Pivot count: {session.get('pivot_count', 0)}/{constraints['max_pivots']}")

    if stage_num == 1:
        synthesizer = Synthesizer()
        skeptic = Skeptic()

        # Restore agent histories if available from previous session
        histories = session.get("agent_histories", {})
        if histories.get("synthesizer"):
            synthesizer.restore(histories["synthesizer"])
            print(f"  Restored Synthesizer history ({len(synthesizer.history)} messages)")
        if histories.get("skeptic"):
            skeptic.restore(histories["skeptic"])
            skeptic.pivot_used = session.get("pivot_used", False)
            print(f"  Restored Skeptic history ({len(skeptic.history)} messages)")

        result = run_stage1(session, synthesizer, skeptic)
        session["stages"]["1"] = result
        session["transcript"] = result.get("transcript", [])
        save_session(session)

        _handle_gate(result, session, None, "", auto_approve=auto_approve, stage_num=1, non_interactive=non_interactive)
    elif stage_num == 2:
        synthesizer = Synthesizer()
        skeptic = Skeptic()

        # Restore Stage 2 agent histories if available
        histories = session.get("agent_histories_stage2", {})
        if histories.get("synthesizer"):
            synthesizer.restore(histories["synthesizer"])
            print(f"  Restored Synthesizer Stage 2 history ({len(synthesizer.history)} messages)")
        if histories.get("skeptic"):
            skeptic.restore(histories["skeptic"])
            skeptic.pivot_used = session.get("pivot_used", False)
            print(f"  Restored Skeptic Stage 2 history ({len(skeptic.history)} messages)")

        result = run_stage2(session, synthesizer, skeptic)
        session["stages"]["2"] = result
        session["transcript"] = result.get("transcript", [])
        save_session(session)

        _handle_gate(result, session, None, "", auto_approve=auto_approve, stage_num=2, non_interactive=non_interactive)
    elif stage_num == 3:
        synthesizer = Synthesizer()
        skeptic = Skeptic()

        # Restore Stage 3 agent histories if available
        histories = session.get("agent_histories_stage3", {})
        if histories.get("synthesizer"):
            synthesizer.restore(histories["synthesizer"])
            print(f"  Restored Synthesizer Stage 3 history ({len(synthesizer.history)} messages)")
        if histories.get("skeptic"):
            skeptic.restore(histories["skeptic"])
            skeptic.pivot_used = session.get("pivot_used", False)
            print(f"  Restored Skeptic Stage 3 history ({len(skeptic.history)} messages)")

        result = run_stage3(session, synthesizer, skeptic)
        session["stages"]["3"] = result
        session["transcript"] = result.get("transcript", [])
        save_session(session)

        _handle_gate(result, session, None, "", auto_approve=auto_approve, stage_num=3, non_interactive=non_interactive)
    elif stage_num == 4:
        synthesizer = Synthesizer()
        skeptic = Skeptic()

        # Restore Stage 4 agent histories if available
        histories = session.get("agent_histories_stage4", {})
        if histories.get("synthesizer"):
            synthesizer.restore(histories["synthesizer"])
            print(f"  Restored Synthesizer Stage 4 history ({len(synthesizer.history)} messages)")
        if histories.get("skeptic"):
            skeptic.restore(histories["skeptic"])
            skeptic.pivot_used = session.get("pivot_used", False)
            print(f"  Restored Skeptic Stage 4 history ({len(skeptic.history)} messages)")

        result = run_stage4(session, synthesizer, skeptic)
        session["stages"]["4"] = result
        session["transcript"] = result.get("transcript", [])
        save_session(session)

        _handle_gate(result, session, None, "", auto_approve=auto_approve, stage_num=4, non_interactive=non_interactive)
    elif stage_num == 5:
        synthesizer = Synthesizer()
        skeptic = Skeptic()

        # Restore Stage 5 agent histories if available
        histories = session.get("agent_histories_stage5", {})
        if histories.get("synthesizer"):
            synthesizer.restore(histories["synthesizer"])
            print(f"  Restored Synthesizer Stage 5 history ({len(synthesizer.history)} messages)")
        if histories.get("skeptic"):
            skeptic.restore(histories["skeptic"])
            skeptic.pivot_used = session.get("pivot_used", False)
            print(f"  Restored Skeptic Stage 5 history ({len(skeptic.history)} messages)")

        result = run_stage5(session, synthesizer, skeptic)
        session["stages"]["5"] = result
        session["transcript"] = result.get("transcript", [])
        save_session(session)

        _handle_gate(result, session, None, "", auto_approve=auto_approve, stage_num=5, non_interactive=non_interactive)
    else:
        print(f"Stage {stage_num} not yet implemented in this version.")


def main():
    parser = argparse.ArgumentParser(
        description="Falsification Engine: Dual-Agent Deliberation for Startup Validation"
    )
    parser.add_argument("--manifest", default="manifest.json",
                        help="Path to manifest JSON (default: manifest.json)")
    parser.add_argument("--niche", default="",
                        help="Optional niche hint or name")
    parser.add_argument("--resume", metavar="SESSION_ID",
                        help="Resume an existing session")
    parser.add_argument("--stage", type=int, default=1,
                        help="Stage to resume from (default: 1)")
    parser.add_argument("--list", action="store_true",
                        help="List all sessions")
    parser.add_argument("--test", action="store_true",
                        help="Test mode: auto-approve gates without human review")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Use file-watching gate instead of terminal prompt (for CI/automation)")
    parser.add_argument("--report", metavar="SESSION_ID",
                        help="Generate final report from an existing completed session")
    parser.add_argument("--refresh-leads", action="store_true",
                        help="Query Supabase for live lead counts and exit")

    args = parser.parse_args()

    if args.report:
        session = load_session(args.report)
        report = generate_final_report(session)
        report_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "sessions",
            f"{session['session_id']}-report.md"
        )
        with open(report_path, "w") as f:
            f.write(report)
        print(f"📄 Report generated: {report_path}")
        return

    if args.refresh_leads:
        from tools import refresh_lead_counts, format_lead_counts
        refresh_lead_counts()
        print(format_lead_counts())
        return

    if args.list:
        list_sessions()
        return

    _check_env()

    if args.resume:
        _run_resume(args.resume, args.stage, auto_approve=args.test, non_interactive=args.non_interactive)
    else:
        _run_new_session(args.manifest, args.niche, auto_approve=args.test, non_interactive=args.non_interactive)


if __name__ == "__main__":
    main()
