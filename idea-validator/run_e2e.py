#!/usr/bin/env python3
"""
End-to-end runner for all 5 falsification engine stages.
Auto-approves gates (--test mode) and chains stages via session IDs.
"""

import subprocess
import sys
import os
import json
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

def run_cmd(cmd: list[str], timeout: int = 1800) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr)."""
    env = os.environ.copy()
    # Parse .env file (handles `export KEY=value` and `KEY=value` syntax)
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Strip `export ` prefix if present
                if line.startswith("export "):
                    line = line[7:]
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip('"').strip("'")
                    env[key] = val
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        env=env,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr


def find_latest_session() -> str:
    """Find the most recently created session file."""
    files = sorted(glob.glob(os.path.join(SESSIONS_DIR, "session_*.json")), reverse=True)
    if not files:
        raise FileNotFoundError("No session files found")
    return os.path.basename(files[0]).replace(".json", "")


def extract_niche_from_session(session_id: str) -> str:
    """Read approved niche from session file."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(path) as f:
        data = json.load(f)
    return data.get("approved_niche", "")


def extract_pain_point_from_session(session_id: str) -> str:
    """Read approved pain point from session file."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(path) as f:
        data = json.load(f)
    return data.get("approved_pain_point", "")


def extract_solution_from_session(session_id: str) -> str:
    """Read approved solution from session file."""
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    with open(path) as f:
        data = json.load(f)
    return data.get("approved_solution", "")


def run_stage(stage_num: int, session_id: str = None, total_stages: int = 5) -> str:
    """Run a single stage and return the session ID."""
    print(f"\n{'='*70}")
    print(f"  STAGE {stage_num}/{total_stages}")
    print(f"{'='*70}")
    
    if stage_num == 1:
        cmd = [sys.executable, "main.py", "--manifest", "manifest.json", "--test"]
    else:
        cmd = [sys.executable, "main.py", "--resume", session_id, "--stage", str(stage_num), "--test"]
    
    exit_code, stdout, stderr = run_cmd(cmd)
    
    # Print output
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    
    if exit_code != 0:
        print(f"\n❌ Stage {stage_num} failed with exit code {exit_code}")
        sys.exit(1)
    
    # Find the session
    if stage_num == 1:
        session_id = find_latest_session()
    
    print(f"\n✅ Stage {stage_num} complete. Session: {session_id}")
    
    if stage_num == 1:
        niche = extract_niche_from_session(session_id)
        print(f"   Approved niche: {niche[:80]}...")
    elif stage_num == 2:
        pp = extract_pain_point_from_session(session_id)
        print(f"   Approved pain point: {pp[:80]}...")
    elif stage_num == 3:
        sol = extract_solution_from_session(session_id)
        print(f"   Approved solution: {sol[:80]}...")
    
    return session_id


def generate_report(session_id: str):
    """Generate the final consolidated report."""
    print(f"\n{'='*70}")
    print(f"  GENERATING FINAL REPORT")
    print(f"{'='*70}")
    
    cmd = [sys.executable, "main.py", "--report", session_id]
    exit_code, stdout, stderr = run_cmd(cmd)
    
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    
    # Find and display the report
    report_path = os.path.join(SESSIONS_DIR, f"{session_id}-report.md")
    if os.path.exists(report_path):
        print(f"\n📄 Report generated: {report_path}")
        with open(report_path) as f:
            content = f.read()
        print(f"\n{'='*70}")
        print("  REPORT PREVIEW (first 2000 chars)")
        print(f"{'='*70}")
        print(content[:2000])
        print(f"\n... ({len(content)} chars total)")
    else:
        print(f"\n⚠️  Report not found at {report_path}")


def main():
    print("="*70)
    print("  FALSIFICATION ENGINE — END-TO-END LIVE RUN")
    print("  Model: Kimi K2.6 via Fireworks.ai")
    print("  Gates: Auto-approved (test mode)")
    print("="*70)
    
    # Stage 1: Niche Alignment
    session_id = run_stage(1)
    
    # Stage 2: Pain Point Research
    session_id = run_stage(2, session_id)
    
    # Stage 3: Solution Design
    session_id = run_stage(3, session_id)
    
    # Stage 4: Business Model & Pricing
    session_id = run_stage(4, session_id)
    
    # Stage 5: Validation Sprint
    session_id = run_stage(5, session_id)
    
    # Generate final report
    generate_report(session_id)
    
    print(f"\n{'='*70}")
    print("  ALL STAGES COMPLETE")
    print(f"  Session ID: {session_id}")
    print(f"  Report: sessions/{session_id}-report.md")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
