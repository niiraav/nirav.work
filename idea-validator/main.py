#!/usr/bin/env python3
"""
idea-validator: Claude (Director) + Kimi K2.6 (Researcher) debate startup ideas
through a 5-stage pipeline and output validated findings to Obsidian.

Usage:
  python main.py --niche "MOT Reminder SaaS" --start-stage 2
  python main.py --mode fresh --lead-focus automotive
  python main.py --resume session_20260517_143022 --stage 3
"""

import argparse
import json
import os
import sys
from datetime import datetime
from config import SESSIONS_DIR, ANTHROPIC_API_KEY, MOONSHOT_API_KEY


def _check_env():
    missing = []
    if not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if not MOONSHOT_API_KEY:
        missing.append("MOONSHOT_API_KEY")
    if missing:
        print(f"Error: missing environment variables: {', '.join(missing)}")
        print("Copy .env.example to .env and fill in your keys, then: source .env")
        sys.exit(1)


def _create_session(niche: str, lead_focus: str, start_stage: int) -> dict:
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {
        "session_id": session_id,
        "niche": niche,
        "lead_focus": lead_focus,
        "created_at": datetime.now().isoformat(),
        "current_stage": start_stage,
        "stages": {},
        "transcript": [],
        "final_confidence": None,
    }


def _load_session(session_id: str) -> dict:
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        print(f"Error: session not found at {path}")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def _list_sessions():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    files = sorted(
        [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")],
        reverse=True,
    )
    if not files:
        print("No sessions found.")
        return
    print("Available sessions:")
    for f in files:
        session_id = f[:-5]
        path = os.path.join(SESSIONS_DIR, f)
        with open(path) as fp:
            data = json.load(fp)
        stage = data.get("current_stage", "?")
        niche = data.get("niche", "unknown")
        created = data.get("created_at", "")[:10]
        print(f"  {session_id}  |  {niche}  |  stage {stage}  |  {created}")


def main():
    parser = argparse.ArgumentParser(
        description="Startup idea validation via Claude + Kimi K2.6 discussion pipeline."
    )
    parser.add_argument("--niche", help="Niche to validate (e.g. 'MOT Reminder SaaS')")
    parser.add_argument(
        "--lead-focus",
        default="",
        help="Lead base segment to bias toward (e.g. automotive, beauty_health)",
    )
    parser.add_argument(
        "--start-stage",
        type=int,
        default=1,
        choices=range(1, 6),
        help="Stage to start from (1-5). Default: 1",
    )
    parser.add_argument(
        "--end-stage",
        type=int,
        default=5,
        choices=range(1, 6),
        help="Stage to stop after (1-5). Default: 5",
    )
    parser.add_argument("--resume", metavar="SESSION_ID", help="Resume an existing session")
    parser.add_argument("--stage", type=int, help="Stage to resume from (used with --resume)")
    parser.add_argument("--list", action="store_true", help="List all sessions")
    parser.add_argument(
        "--mode",
        choices=["fresh"],
        help="Mode: 'fresh' starts a new session with lead-focus guidance",
    )

    args = parser.parse_args()

    if args.list:
        _list_sessions()
        return

    _check_env()

    from orchestrator import run_session

    if args.resume:
        session = _load_session(args.resume)
        start_stage = args.stage or session.get("current_stage", 1)
        end_stage = args.end_stage
        print(f"\nResuming session: {args.resume}")
        print(f"Niche: {session['niche']}  |  Resuming from stage {start_stage}")
    else:
        niche = args.niche
        if not niche:
            if args.mode == "fresh":
                niche = input("Enter the niche or idea to validate: ").strip()
            else:
                print("Error: --niche is required (or use --mode fresh for interactive input).")
                parser.print_help()
                sys.exit(1)
        start_stage = args.start_stage
        end_stage = args.end_stage
        session = _create_session(niche, args.lead_focus, start_stage)
        print(f"\nNew session: {session['session_id']}")
        print(f"Niche: {niche}  |  Stages {start_stage}–{end_stage}")

    try:
        run_session(session, start_stage=start_stage, end_stage=end_stage)
    except KeyboardInterrupt:
        print("\n\nInterrupted. Session progress saved.")
        sys.exit(0)


if __name__ == "__main__":
    main()
