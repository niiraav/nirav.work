"""
Gate Manager: generates human gate markdown, launches $EDITOR, watches for save,
extracts decisions, and logs to Obsidian vault.
"""

import os
import re
import time
import json
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from config import GATES_DIR, OBSIDIAN_VAULT_PATH


class GateManager:
    """Manages human gate lifecycle: generate -> open -> watch -> extract -> log."""

    def __init__(self):
        os.makedirs(GATES_DIR, exist_ok=True)
        os.makedirs(OBSIDIAN_VAULT_PATH, exist_ok=True)

    def _gate_path(self, stage_num: int, session_id: str) -> str:
        return os.path.join(
            GATES_DIR,
            f"stage{stage_num}",
            f"gate-stage{stage_num}-{session_id}.md"
        )

    def _decision_path(self, stage_num: int, session_id: str) -> str:
        return os.path.join(
            GATES_DIR,
            f"stage{stage_num}",
            f"gate-stage{stage_num}-{session_id}-decision.json"
        )

    def generate_stage1_gate(
        self,
        session_id: str,
        synthesizer_ranking: list,
        skeptic_ranking: list,
        convergence_type: str,
        niches: Dict[str, Any],
        kill_conditions: list,
        rejected_niches: list,
        unverified_claims: list,
        evidence_status: list,
        momentum_summary: list,
        transcript_summary: str,
        raw_synthesizer_r1: str = "",
        raw_skeptic_r1: str = "",
    ) -> str:
        """Generate Stage 1 gate markdown and return the file path."""
        os.makedirs(os.path.join(GATES_DIR, "stage1"), exist_ok=True)

        max_len = max(len(synthesizer_ranking), len(skeptic_ranking))
        rank_rows = []
        for i in range(max_len):
            s = synthesizer_ranking[i] if i < len(synthesizer_ranking) else "—"
            sk = skeptic_ranking[i] if i < len(skeptic_ranking) else "—"
            match = "✅" if s != "—" and sk != "—" and s == sk else "❌" if s != "—" and sk != "—" else ""
            rank_rows.append(f"| {i+1} | {s} | {sk} | {match} |")
        rank_table = "\n".join(rank_rows)

        kill_rows = []
        for kc in kill_conditions:
            status_emoji = "✅" if kc.get("status") == "active" else "⚠️"
            kill_rows.append(f"| {kc.get('id','?')} | {kc.get('condition','?')} | {status_emoji} | {kc.get('evidence','—')} |")
        kill_table = "\n".join(kill_rows) if kill_rows else "| — | — | — | — |"

        uv_lines = []
        for uv in unverified_claims:
            priority = "**BLOCKING**" if uv.get("priority") == "blocking" else "Nice-to-have"
            uv_lines.append(f"| {uv.get('claim','?')} | {uv.get('introduced_by','?')} | {priority} |")
        uv_table = "\n".join(uv_lines) if uv_lines else "| — | — | — |"

        ev_lines = []
        for ev in evidence_status:
            status = "✅ Resolved" if ev.get("status") == "resolved" else "❌ Pending"
            ev_lines.append(f"| {ev.get('field','?')} | {status} | {ev.get('value','—')} |")
        ev_table = "\n".join(ev_lines) if ev_lines else "| — | — | — |"

        mom_lines = []
        for r in momentum_summary:
            h = r.get('health')
            health = f"{h:.2f}" if h is not None else "N/A"
            if h is None:
                label = "stable"
            elif h > 0.2:
                label = "converging"
            elif h < -0.2:
                label = "deteriorating"
            else:
                label = "deadlock"
            mom_lines.append(f"| {r['turn']} | {r['raised']} | {r['resolved']} | {health} | {label} |")
        mom_table = "\n".join(mom_lines) if mom_lines else "| — | — | — | — | — |"

        rej_lines = []
        for r in rejected_niches:
            rej_lines.append(f"| {r.get('niche','?')} | {r.get('rejected_by','?')} | {r.get('reason','?')} |")
        rej_table = "\n".join(rej_lines) if rej_lines else "| — | — | — |"

        content = f"""# STAGE 1 GATE: Niche Alignment
**Session:** {session_id}
**Generated:** {datetime.now().isoformat()}
**Convergence Type:** {convergence_type}

---

## Blind Rankings

| Rank | Synthesizer | Skeptic | Match? |
|------|-------------|---------|--------|
{rank_table}

---

## Selected Niche
**{synthesizer_ranking[0] if synthesizer_ranking else '—'}**

(Synthesizer's #1; Skeptic's #1: {skeptic_ranking[0] if skeptic_ranking else '—'})

---

## Signed-off Kill Conditions

| ID | Condition | Status | Evidence |
|----|-----------|--------|----------|
{kill_table}

---

## [unverified] Claims → Stage 2 Research Agenda

| Claim | Introduced By | Priority |
|-------|---------------|----------|
{uv_table}

---

## Required Evidence Status

| Field | Status | Value |
|-------|--------|-------|
{ev_table}

---

## Rejected Niches

| Niche | Rejected By | Reason |
|-------|-------------|--------|
{rej_table}

---

## Convergence Health

| Round | Raised | Resolved | Health | Signal |
|-------|--------|----------|--------|--------|
{mom_table}

---

## Transcript Summary

{transcript_summary}

---

## Raw Proposals (for human verification)

<details>
<summary>Synthesizer Round 1 (click to expand)</summary>

```
{raw_synthesizer_r1[:1200]}
```

</details>

<details>
<summary>Skeptic Round 1 (click to expand)</summary>

```
{raw_skeptic_r1[:1200]}
```

</details>

---

## YOUR DECISION

**[ ] APPROVE** — Advance to Stage 2 with top-ranked niche as primary

**[ ] REFINE** — Specify what to change:
> _________________________________

**[ ] REJECT** — Reason (will write to manifest as authoritative constraint):
> _________________________________

---

*Save this file to submit your decision.*
*This gate will be logged to your Obsidian vault as a permanent decision record.*
"""
        path = self._gate_path(1, session_id)
        with open(path, "w") as f:
            f.write(content)
        return path

    def open_gate(self, path: str):
        """Open the gate markdown in the default $EDITOR."""
        editor = os.environ.get("EDITOR")
        if editor:
            subprocess.Popen([editor, path])
        else:
            subprocess.Popen(["open", "-W", "-n", path])

    def watch_for_save(self, path: str, poll_interval: float = 1.0, timeout: float = 300.0) -> bool:
        """Watch the gate file for modification. Returns True if saved within timeout."""
        if not os.path.exists(path):
            return False
        initial_mtime = os.path.getmtime(path)
        elapsed = 0.0
        print(f"\n⏳ Waiting for you to save the gate file: {path}")
        print(f"   (Checking every {poll_interval}s, timeout {timeout}s)")
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval
            current_mtime = os.path.getmtime(path)
            if current_mtime > initial_mtime:
                print("   ✓ Gate file saved.")
                return True
            if int(elapsed) % 30 == 0 and elapsed > 0:
                print(f"   ... still waiting ({int(elapsed)}s elapsed)")
        print("   ⚠️ Timeout waiting for save.")
        return False

    def extract_decision(self, path: str) -> Dict[str, Any]:
        """Parse the gate markdown and extract the human decision."""
        with open(path) as f:
            content = f.read()

        decision = {
            "decision": "pending",
            "rationale": "",
            "timestamp": datetime.now().isoformat(),
        }

        if "[x] APPROVE" in content.lower() or "[X] APPROVE" in content:
            decision["decision"] = "approve"
        elif "[x] REFINE" in content.lower() or "[X] REFINE" in content:
            decision["decision"] = "refine"
            match = re.search(r"REFINE.*?(?:\n|\r)>\s*(.+?)(?:\n\n|\n---|\Z)", content, re.DOTALL | re.IGNORECASE)
            if match:
                decision["rationale"] = match.group(1).strip()
        elif "[x] REJECT" in content.lower() or "[X] REJECT" in content:
            decision["decision"] = "reject"
            match = re.search(r"REJECT.*?(?:\n|\r)>\s*(.+?)(?:\n\n|\n---|\Z)", content, re.DOTALL | re.IGNORECASE)
            if match:
                decision["rationale"] = match.group(1).strip()

        session_id = os.path.basename(path).replace("gate-stage1-", "").replace(".md", "")
        stage_num = 1
        decision_path = self._decision_path(stage_num, session_id)
        with open(decision_path, "w") as f:
            json.dump(decision, f, indent=2)

        return decision

    def log_to_obsidian(self, session_id: str, stage_num: int, gate_path: str, decision: Dict[str, Any]):
        """Copy the gate markdown to the Obsidian vault as a permanent decision log."""
        today = datetime.now().strftime("%Y-%m-%d")
        obsidian_filename = f"{today}-gate-stage{stage_num}-{session_id}.md"
        obsidian_path = os.path.join(OBSIDIAN_VAULT_PATH, obsidian_filename)

        with open(gate_path) as f:
            gate_content = f.read()

        log_content = gate_content + f"""

---

## Decision Record

**Decision:** {decision.get('decision', 'unknown').upper()}
**Rationale:** {decision.get('rationale', '—')}
**Timestamp:** {decision.get('timestamp', datetime.now().isoformat())}
**Logged to vault:** {obsidian_path}
"""

        with open(obsidian_path, "w") as f:
            f.write(log_content)

        print(f"\n📝 Gate logged to Obsidian: {obsidian_path}")

    def generate_stage2_gate(
        self,
        session_id: str,
        approved_niche: str,
        pain_points: list,
        convergence_type: str,
        kill_conditions: list,
        unverified_claims: list,
        evidence_status: list,
        transcript_summary: str,
        search_evidence: Dict[str, Any] = None,
    ) -> str:
        """Generate Stage 2 gate markdown and return the file path."""
        os.makedirs(os.path.join(GATES_DIR, "stage2"), exist_ok=True)

        pp_rows = []
        for i, pp in enumerate(pain_points[:5], 1):
            name = pp.get('name', '?')
            status = pp.get('status', 'proposed')
            status_emoji = "✅" if status == "validated" else "⚠️"
            pp_rows.append(f"| {i} | {name} | {status_emoji} |")
        pp_table = "\n".join(pp_rows) if pp_rows else "| — | — | — |"

        uv_lines = []
        for uv in unverified_claims:
            priority = "**BLOCKING**" if uv.get("priority") == "blocking" else "Nice-to-have"
            uv_lines.append(f"| {uv.get('claim','?')} | {uv.get('introduced_by','?')} | {priority} |")
        uv_table = "\n".join(uv_lines) if uv_lines else "| — | — | — |"

        ev_lines = []
        for ev in evidence_status:
            status = "✅ Resolved" if ev.get("status") == "resolved" else "❌ Pending"
            ev_lines.append(f"| {ev.get('field','?')} | {status} | {ev.get('value','—')} |")
        ev_table = "\n".join(ev_lines) if ev_lines else "| — | — | — |"

        kill_rows = []
        for kc in kill_conditions:
            status_emoji = "✅" if kc.get("status") == "active" else "⚠️"
            kill_rows.append(f"| {kc.get('id','?')} | {kc.get('condition','?')} | {status_emoji} |")
        kill_table = "\n".join(kill_rows) if kill_rows else "| — | — | — |"

        search_lines = []
        if search_evidence:
            for category, items in search_evidence.items():
                search_lines.append(f"\n**{category.upper().replace('_', ' ')}** ({len(items)} results)")
                for i, item in enumerate(items[:3], 1):
                    title = item.get('title', 'Untitled')[:60]
                    href = item.get('href', '')
                    search_lines.append(f"  {i}. [{title}]({href})")
        search_md = "\n".join(search_lines) if search_lines else "*(No web search evidence collected)*"

        content = f"""# STAGE 2 GATE: Pain Point Research
**Session:** {session_id}
**Generated:** {datetime.now().isoformat()}
**Convergence Type:** {convergence_type}
**Approved Niche (from Stage 1):** {approved_niche}

---

## Approved Niche
**{approved_niche}**

---

## Web Search Evidence (Sources Consulted)

{search_md}

---

## Proposed Pain Points

| Rank | Pain Point | Status |
|------|-----------|--------|
{pp_table}

---

## Carry-Forward Kill Conditions

| ID | Condition | Status |
|----|-----------|--------|
{kill_table}

---

## [unverified] Claims → Stage 3 Research Agenda

| Claim | Introduced By | Priority |
|-------|---------------|----------|
{uv_table}

---

## Required Evidence Status

| Field | Status | Value |
|-------|--------|-------|
{ev_table}

---

## Transcript Summary

{transcript_summary}

---

## YOUR DECISION

**[ ] APPROVE** — Advance to Stage 3 (Solution Design) with top-ranked pain point as primary

**[ ] REFINE** — Specify what to change:
> _________________________________

**[ ] REJECT** — Abandon this niche and return to Stage 1 (will write to manifest as constraint):
> _________________________________

---

*Save this file to submit your decision.*
*This gate will be logged to your Obsidian vault as a permanent decision record.*
"""
        path = self._gate_path(2, session_id)
        with open(path, "w") as f:
            f.write(content)
        return path

    def prompt_human_decision(self, stage_num: int, gate_data: Dict[str, Any]) -> Dict[str, Any]:
        """Interactive terminal prompt for gate decisions."""
        import sys
        
        print("\n" + "="*70)
        print(f"  STAGE {stage_num} GATE: Human Review Required")
        print("="*70)
        
        if stage_num == 1:
            synth_ranking = gate_data.get("synthesizer_ranking", [])
            sk_ranking = gate_data.get("skeptic_ranking", [])
            kc_count = len(gate_data.get("kill_conditions", []))
            uv_count = len(gate_data.get("unverified_claims", []))
            
            print(f"\n  Top Niche: {synth_ranking[0] if synth_ranking else '—'}")
            print(f"  Convergence: {gate_data.get('convergence_type', 'unknown')}")
            print(f"  Kill Conditions: {kc_count}")
            print(f"  Unverified Claims: {uv_count}")
            
        elif stage_num == 2:
            niche = gate_data.get("approved_niche", "—")
            pain_points = gate_data.get("pain_points", [])
            top_pp = pain_points[0].get("name", "—") if pain_points else "—"
            uv_count = len(gate_data.get("unverified_claims", []))
            
            print(f"\n  Niche: {niche}")
            print(f"  Top Pain Point: {top_pp}")
            print(f"  Pain Points Found: {len(pain_points)}")
            print(f"  Unverified Claims: {uv_count}")
            
        elif stage_num == 3:
            niche = gate_data.get("approved_niche", "—")
            pp = gate_data.get("approved_pain_point", "—")
            solutions = gate_data.get("solutions", [])
            top_sol = solutions[0].get("name", "—") if solutions else "—"
            
            print(f"\n  Niche: {niche}")
            print(f"  Pain Point: {pp}")
            print(f"  Top Solution: {top_sol}")
            print(f"  Solutions Found: {len(solutions)}")
            
        elif stage_num == 4:
            niche = gate_data.get("approved_niche", "—")
            pp = gate_data.get("approved_pain_point", "—")
            sol = gate_data.get("approved_solution", "—")
            tiers = gate_data.get("pricing_tiers", [])
            ue = gate_data.get("unit_economics", {})
            cac_tier = ue.get("cac_tier") if ue else None
            cac_kill = gate_data.get("cac_kill_triggered", False)
            
            print(f"\n  Niche: {niche}")
            print(f"  Pain Point: {pp}")
            print(f"  Solution: {sol}")
            print(f"  Pricing Tiers Found: {len(tiers)}")
            if tiers:
                for t in tiers[:3]:
                    price_display = t.get("price_str", f"£{t.get('price', '?')}")
                    print(f"    - {t['name']}: {price_display}/{t.get('period', 'month')}")
            if ue and ue.get("cac") is not None:
                tier_label = {"safe": "✅ SAFE", "weak": "⚠️ WEAK", "kill": "⛔ KILL"}.get(cac_tier, "?")
                print(f"  CAC: £{ue['cac']:.0f} {tier_label}")
                if ue.get("ltv") is not None:
                    print(f"  LTV: £{ue['ltv']:.0f}, Ratio: {ue['ltv']/ue['cac']:.1f}")
                if ue.get("gross_margin") is not None:
                    print(f"  Gross Margin: {ue['gross_margin']:.0f}%")
            if cac_kill:
                print(f"\n  ⛔ CAC KILL TRIGGERED — business model fails manifest constraints")
                
        elif stage_num == 5:
            niche = gate_data.get("approved_niche", "—")
            pp = gate_data.get("approved_pain_point", "—")
            sol = gate_data.get("approved_solution", "—")
            experiments = gate_data.get("experiments", [])
            sprint_duration = gate_data.get("sprint_duration_days", 30)
            
            print(f"\n  Niche: {niche}")
            print(f"  Pain Point: {pp}")
            print(f"  Solution: {sol}")
            print(f"  Sprint Duration: {sprint_duration} days")
            print(f"  Experiments Found: {len(experiments)}")
            for i, exp in enumerate(experiments[:3], 1):
                print(f"    {i}. {exp['name'][:50]} ({exp['duration'] or 'no duration'})")
        
        gate_path = self._gate_path(stage_num, gate_data.get("session_id", "unknown"))
        print(f"\n  Full gate document: {gate_path}")
        
        print("\n" + "-"*70)
        print("  [a] Approve — advance to next stage")
        print("  [r] Refine — specify what to change")
        print("  [x] Reject — abandon current path")
        print("-"*70)
        
        while True:
            try:
                choice = input("\n  > ").strip().lower()
                
                if choice in ("a", "approve"):
                    return {
                        "decision": "approve",
                        "rationale": "Approved via terminal prompt.",
                        "timestamp": datetime.now().isoformat(),
                    }
                elif choice in ("r", "refine"):
                    rationale = input("  Refinement details: ").strip()
                    return {
                        "decision": "refine",
                        "rationale": rationale or "Refinement requested via terminal prompt.",
                        "timestamp": datetime.now().isoformat(),
                    }
                elif choice in ("x", "reject"):
                    rationale = input("  Rejection reason: ").strip()
                    return {
                        "decision": "reject",
                        "rationale": rationale or "Rejected via terminal prompt.",
                        "timestamp": datetime.now().isoformat(),
                    }
                elif choice == "":
                    print("  Please enter a, r, or x.")
                else:
                    print("  Invalid choice. Enter [a]pprove, [r]efine, or [x]reject.")
                    
            except KeyboardInterrupt:
                print("\n\n  Interrupted. Returning timeout decision.")
                return {
                    "decision": "timeout",
                    "rationale": "User interrupted (Ctrl+C).",
                    "timestamp": datetime.now().isoformat(),
                }
            except EOFError:
                print("\n  Non-interactive environment detected. Returning timeout.")
                return {
                    "decision": "timeout",
                    "rationale": "Non-interactive terminal.",
                    "timestamp": datetime.now().isoformat(),
                }

    def run_gate(self, stage_num: int, session_id: str, gate_data: Dict[str, Any], auto_approve: bool = False, non_interactive: bool = False) -> Dict[str, Any]:
        """Full gate lifecycle: generate, prompt/watch, extract, log."""
        gate_data = dict(gate_data)
        gate_data["session_id"] = session_id
        
        if stage_num == 1:
            path = self.generate_stage1_gate(**gate_data)
        elif stage_num == 2:
            path = self.generate_stage2_gate(**gate_data)
        elif stage_num == 3:
            path = self.generate_stage3_gate(**gate_data)
        elif stage_num == 4:
            path = self.generate_stage4_gate(**gate_data)
        elif stage_num == 5:
            path = self.generate_stage5_gate(**gate_data)
        else:
            raise NotImplementedError(f"Gate generation for stage {stage_num} not yet implemented.")

        convergence_type = gate_data.get("convergence_type", "unknown")
        is_disputed = convergence_type in ("disputed", "diverging")

        if auto_approve:
            print(f"\n  [TEST MODE] Gate generated: {path}")
            if is_disputed:
                print(f"  ⚠️  [TEST MODE] Convergence is DISPUTED — would require human adjudication in real run.")
            print("  [TEST MODE] Auto-approving without human review.")
            decision = {
                "decision": "approve",
                "rationale": f"Auto-approved in test mode. (Convergence: {convergence_type})",
                "timestamp": datetime.now().isoformat(),
            }
            decision_path = self._decision_path(stage_num, session_id)
            with open(decision_path, "w") as f:
                json.dump(decision, f, indent=2)
            self.log_to_obsidian(session_id, stage_num, path, decision)
            return decision

        # Force interactive terminal prompt when convergence is disputed,
        # even if --non-interactive was passed. Disputed convergence requires
        # human adjudication — file-watching is not appropriate.
        if is_disputed and non_interactive:
            print(f"\n  ⚠️  Convergence is {convergence_type.upper()}. Forcing interactive gate.")
            print(f"  (Disputed convergence cannot be auto-resolved via file-watching.)")
            decision = self.prompt_human_decision(stage_num, gate_data)
        elif non_interactive:
            self.open_gate(path)
            saved = self.watch_for_save(path)
            if not saved:
                print("Gate not saved in time. Returning pending decision.")
                return {"decision": "timeout", "rationale": "Human did not respond in time"}
            decision = self.extract_decision(path)
        else:
            decision = self.prompt_human_decision(stage_num, gate_data)
        
        decision_path = self._decision_path(stage_num, session_id)
        with open(decision_path, "w") as f:
            json.dump(decision, f, indent=2)
        
        self.log_to_obsidian(session_id, stage_num, path, decision)
        return decision

    def generate_stage3_gate(
        self,
        session_id: str,
        approved_niche: str,
        approved_pain_point: str,
        solutions: list,
        convergence_type: str,
        kill_conditions: list,
        unverified_claims: list,
        evidence_status: list,
        transcript_summary: str,
    ) -> str:
        """Generate Stage 3 gate markdown and return the file path."""
        os.makedirs(os.path.join(GATES_DIR, "stage3"), exist_ok=True)

        sol_rows = []
        for i, sol in enumerate(solutions[:5], 1):
            name = sol.get('name', '?')
            status = sol.get('status', 'proposed')
            status_emoji = "✅" if status == "validated" else "⚠️"
            sol_rows.append(f"| {i} | {name} | {status_emoji} |")
        sol_table = "\n".join(sol_rows) if sol_rows else "| — | — | — |"

        uv_lines = []
        for uv in unverified_claims:
            priority = "**BLOCKING**" if uv.get("priority") == "blocking" else "Nice-to-have"
            uv_lines.append(f"| {uv.get('claim','?')} | {uv.get('introduced_by','?')} | {priority} |")
        uv_table = "\n".join(uv_lines) if uv_lines else "| — | — | — |"

        ev_lines = []
        for ev in evidence_status:
            status = "✅ Resolved" if ev.get("status") == "resolved" else "❌ Pending"
            ev_lines.append(f"| {ev.get('field','?')} | {status} | {ev.get('value','—')} |")
        ev_table = "\n".join(ev_lines) if ev_lines else "| — | — | — |"

        kill_rows = []
        for kc in kill_conditions:
            status_emoji = "✅" if kc.get("status") == "active" else "⚠️"
            kill_rows.append(f"| {kc.get('id','?')} | {kc.get('condition','?')} | {status_emoji} |")
        kill_table = "\n".join(kill_rows) if kill_rows else "| — | — | — |"

        content = f"""# STAGE 3 GATE: Solution Design
**Session:** {session_id}
**Generated:** {datetime.now().isoformat()}
**Convergence Type:** {convergence_type}
**Approved Niche (from Stage 1):** {approved_niche}
**Approved Pain Point (from Stage 2):** {approved_pain_point}

---

## Proposed Solutions

| Rank | Solution | Status |
|------|----------|--------|
{sol_table}

---

## Carry-Forward Kill Conditions

| ID | Condition | Status |
|----|-----------|--------|
{kill_table}

---

## [unverified] Claims → Stage 4 Research Agenda

| Claim | Introduced By | Priority |
|-------|---------------|----------|
{uv_table}

---

## Required Evidence Status

| Field | Status | Value |
|-------|--------|-------|
{ev_table}

---

## Transcript Summary

{transcript_summary}

---

## YOUR DECISION

**[ ] APPROVE** — Advance to Stage 4 with top-ranked solution as primary

**[ ] REFINE** — Specify what to change:
> _________________________________

**[ ] REJECT** — Return to Stage 2 (will write rationale to session):
> _________________________________

---

*Save this file to submit your decision.*
*This gate will be logged to your Obsidian vault as a permanent decision record.*
"""
        path = self._gate_path(3, session_id)
        with open(path, "w") as f:
            f.write(content)
        return path

    def generate_stage4_gate(
        self,
        session_id: str,
        approved_niche: str,
        approved_pain_point: str,
        approved_solution: str,
        pricing_tiers: list,
        unit_economics: Dict[str, Any],
        cac_tier: Optional[str],
        cac_kill_triggered: bool,
        convergence_type: str,
        kill_conditions: list,
        unverified_claims: list,
        evidence_status: list,
        transcript_summary: str,
    ) -> str:
        """Generate Stage 4 gate markdown and return the file path."""
        os.makedirs(os.path.join(GATES_DIR, "stage4"), exist_ok=True)

        tier_rows = []
        for i, tier in enumerate(pricing_tiers[:5], 1):
            name = tier.get('name', '?')
            price = tier.get('price_str', '?')
            period = tier.get('period', 'month')
            desc = tier.get('description', '')[:60]
            tier_rows.append(f"| {i} | {name} | {price}/{period} | {desc} |")
        tier_table = "\n".join(tier_rows) if tier_rows else "| — | — | — | — |"

        ue = unit_economics or {}
        cac = ue.get('cac')
        ltv = ue.get('ltv')
        margin = ue.get('gross_margin')
        payback = ue.get('payback_months')
        cac_tier_label = {"safe": "✅ Safe (≤£50)", "weak": "⚠️ Weak (£50-100)", "kill": "⛔ KILL (>£100)", None: "—"}.get(cac_tier, "—")

        ue_lines = []
        if cac is not None:
            ue_lines.append(f"| CAC | £{cac:.0f} | {cac_tier_label} |")
        if ltv is not None:
            ue_lines.append(f"| LTV | £{ltv:.0f} | {'✅' if ltv > 3*(cac or 0) else '⚠️'} |")
        if margin is not None:
            ue_lines.append(f"| Gross Margin | {margin:.0f}% | {'✅' if margin >= 70 else '⚠️'} |")
        if payback is not None:
            ue_lines.append(f"| Payback Period | {payback:.1f} mo | {'✅' if payback <= 12 else '⚠️'} |")
        ue_table = "\n".join(ue_lines) if ue_lines else "| — | — | — |"

        cac_banner = ""
        if cac_kill_triggered:
            cac_banner = f"""
⚠️ **CAC KILL TRIGGERED**

The proposed CAC of £{cac:.0f} exceeds the £100 auto-kill threshold.
The business model as presented **fails manifest constraints**.
The Synthesizer must revise acquisition channels or pricing before this can advance.
"""
        elif cac_tier == "weak":
            cac_banner = f"""
⚠️ **CAC WEAK ZONE**

The proposed CAC of £{cac:.0f} is in the £50–100 range. This is borderline —
requires strong LTV or fast payback to justify.
"""

        kill_rows = []
        for kc in kill_conditions:
            status_emoji = "✅" if kc.get("status") == "active" else "⚠️"
            kill_rows.append(f"| {kc.get('id','?')} | {kc.get('condition','?')} | {status_emoji} |")
        kill_table = "\n".join(kill_rows) if kill_rows else "| — | — | — |"

        uv_lines = []
        for uv in unverified_claims:
            priority = "**BLOCKING**" if uv.get("priority") == "blocking" else "Nice-to-have"
            uv_lines.append(f"| {uv.get('claim','?')} | {uv.get('introduced_by','?')} | {priority} |")
        uv_table = "\n".join(uv_lines) if uv_lines else "| — | — | — |"

        ev_lines = []
        for ev in evidence_status:
            status = "✅ Resolved" if ev.get("status") == "resolved" else "❌ Pending"
            ev_lines.append(f"| {ev.get('field','?')} | {status} | {ev.get('value','—')} |")
        ev_table = "\n".join(ev_lines) if ev_lines else "| — | — | — |"

        content = f"""# STAGE 4 GATE: Business Model & Pricing
**Session:** {session_id}
**Generated:** {datetime.now().isoformat()}
**Convergence Type:** {convergence_type}
**Approved Niche (from Stage 1):** {approved_niche}
**Approved Pain Point (from Stage 2):** {approved_pain_point}
**Approved Solution (from Stage 3):** {approved_solution}

---

## Pricing Tiers

| # | Tier | Price | Description |
|---|------|-------|-------------|
{tier_table}

---

## Unit Economics

| Metric | Value | Assessment |
|--------|-------|------------|
{ue_table}

{cac_banner}

---

## Carry-Forward Kill Conditions

| ID | Condition | Status |
|----|-----------|--------|
{kill_table}

---

## [unverified] Claims → Validation Sprint Agenda

| Claim | Introduced By | Priority |
|-------|---------------|----------|
{uv_table}

---

## Required Evidence Status

| Field | Status | Value |
|-------|--------|-------|
{ev_table}

---

## Transcript Summary

{transcript_summary}

---

## YOUR DECISION

**[ ] APPROVE** — Advance to Stage 5 (Validation Sprint) with this business model

**[ ] REFINE** — Specify what to change (especially if CAC needs revision):
> _________________________________

**[ ] REJECT** — Return to Stage 3 (will write rationale to session):
> _________________________________

---

*Save this file to submit your decision.*
*This gate will be logged to your Obsidian vault as a permanent decision record.*
"""
        path = self._gate_path(4, session_id)
        with open(path, "w") as f:
            f.write(content)
        return path

    def generate_stage5_gate(
        self,
        session_id: str,
        approved_niche: str,
        approved_pain_point: str,
        approved_solution: str,
        approved_business_model: Dict[str, Any],
        experiments: list,
        sprint_duration_days: int,
        convergence_type: str,
        kill_conditions: list,
        unverified_claims: list,
        evidence_status: list,
        transcript_summary: str,
    ) -> str:
        """Generate Stage 5 gate markdown and return the file path."""
        os.makedirs(os.path.join(GATES_DIR, "stage5"), exist_ok=True)

        exp_rows = []
        for i, exp in enumerate(experiments[:5], 1):
            name = exp.get('name', '?')[:60]
            hypothesis = exp.get('hypothesis', '')[:80]
            metric = exp.get('metric', '')[:50]
            success = exp.get('success_criteria', '')[:50]
            duration = exp.get('duration', '—')[:30]
            exp_rows.append(f"| {i} | {name} | {hypothesis} | {metric} | {success} | {duration} |")
        exp_table = "\n".join(exp_rows) if exp_rows else "| — | — | — | — | — | — |"

        bm = approved_business_model or {}
        pricing = bm.get("pricing_tiers", [])
        ue = bm.get("unit_economics", {})
        def _format_price(t):
            price = t.get("price_str", f"£{t.get('price', '?')}")
            return f"{t['name']} ({price}/{t.get('period', 'month')})"
        tier_summary = ", ".join([_format_price(t) for t in pricing[:3]]) if pricing else "—"
        ue_summary = f"CAC £{ue.get('cac', '?')}" if ue.get("cac") else "—"

        kill_rows = []
        for kc in kill_conditions:
            status_emoji = "✅" if kc.get("status") == "active" else "⚠️"
            kill_rows.append(f"| {kc.get('id','?')} | {kc.get('condition','?')} | {status_emoji} |")
        kill_table = "\n".join(kill_rows) if kill_rows else "| — | — | — |"

        uv_lines = []
        for uv in unverified_claims:
            priority = "**BLOCKING**" if uv.get("priority") == "blocking" else "Nice-to-have"
            uv_lines.append(f"| {uv.get('claim','?')} | {uv.get('introduced_by','?')} | {priority} |")
        uv_table = "\n".join(uv_lines) if uv_lines else "| — | — | — |"

        ev_lines = []
        for ev in evidence_status:
            status = "✅ Resolved" if ev.get("status") == "resolved" else "❌ Pending"
            ev_lines.append(f"| {ev.get('field','?')} | {status} | {ev.get('value','—')} |")
        ev_table = "\n".join(ev_lines) if ev_lines else "| — | — | — |"

        content = f"""# STAGE 5 GATE: Validation Sprint Design
**Session:** {session_id}
**Generated:** {datetime.now().isoformat()}
**Convergence Type:** {convergence_type}
**Sprint Duration:** {sprint_duration_days} days

---

## Approved Artifacts (Carried Forward)

| Stage | Artifact |
|-------|----------|
| 1 | **{approved_niche[:80]}** |
| 2 | **{approved_pain_point[:80]}** |
| 3 | **{approved_solution[:80]}** |
| 4 | {tier_summary} | {ue_summary} |

---

## Validation Experiments

| # | Experiment | Hypothesis | Metric | Success Criteria | Duration |
|---|-----------|------------|--------|----------------- |----------|
{exp_table}

---

## Carry-Forward Kill Conditions

| ID | Condition | Status |
|----|-----------|--------|
{kill_table}

---

## [unverified] Claims → Sprint Execution Notes

| Claim | Introduced By | Priority |
|-------|---------------|----------|
{uv_table}

---

## Required Evidence Status

| Field | Status | Value |
|-------|--------|-------|
{ev_table}

---

## Transcript Summary

{transcript_summary}

---

## YOUR DECISION

**[ ] APPROVE** — Final gate passed. Generate consolidated validation report and proceed to execution.

**[ ] REFINE** — Specify experiments to revise or replace:
> _________________________________

**[ ] REJECT** — Return to Stage 4 (business model needs rethinking):
> _________________________________

---

*Save this file to submit your decision.*
*This gate will be logged to your Obsidian vault as a permanent decision record.*
"""
        path = self._gate_path(5, session_id)
        with open(path, "w") as f:
            f.write(content)
        return path
