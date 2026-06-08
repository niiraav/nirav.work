# E2E Agent Loop Framework — Critique

**Date:** 2026-06-08

---

## Top 3 Criticisms (ranked by severity)

---

### #1 — EXECUTE has no failure recovery path (severity: loop-killing)

When Hermes hits a blocker — test fails 3x in a row, dependency conflict, API signature changed, context overflow mid-file — there is no defined behavior. No exit condition, no escalation signal, no sub-loop ceiling. The autonomous phase either spins indefinitely or halts silently. You won't know which until you check.

**Proposed fix:** Add a hard exit condition in the Hermes EXECUTE prompt: "After N consecutive test failures, write `BLOCKED.md` with diagnosis (what failed, what you tried, confidence in root cause) and halt." This creates an implicit 4th gate — but it's an exception path, not a happy-path gate, so it doesn't violate your 3-gate goal.

**Cost:** 30 minutes of prompt engineering + adding `BLOCKED.md` as a convention to `STATE.md`.

**Worth it:** Non-negotiable. This is the difference between a loop and a job that hangs.

---

### #2 — Copy-paste handoff breaks the "autonomous" claim (severity: architectural)

Copy-pasting between Claude and Hermes isn't just friction — it's you as a synchronization primitive. Every paste is a chance for truncation, formatting loss, or you simply not doing it fast enough. You've built a human-in-the-loop system that calls itself autonomous, then put the human in the hot path, not just at gates.

**Proposed fix:** Claude Code CLI supports non-interactive use: `claude --print -p "$(cat hermes_prompt.md)" < context.md > plan.md`. Hermes invokes this as a subprocess and reads `plan.md` directly. No copy-paste. Claude Pro subscription value is preserved; the interaction is just shell-mediated instead of clipboard-mediated.

**Cost:** Hermes needs a subprocess call + stdout capture + error handling for non-zero exits. Medium effort, one-time.

**Worth it:** Yes. This is the unlock that makes the loop actually autonomous between PLAN and EXECUTE.

---

### #3 — STATE.md becomes write-only noise after 3-4 cycles (severity: context decay)

By cycle 4, `STATE.md` is 600+ lines. Any agent reading it for context will silently drop or hallucinate older sections — context windows truncate from the top, not the bottom. You'll get Hermes making decisions based on stale phase data with no signal that it's doing so.

**Proposed fix:** Split the single file into two:
- `STATE.md` — current phase only (< 100 lines, always fresh, human-readable)
- `HISTORY.jsonl` — append-only structured log of phase transitions and decisions (machine-readable, never read in full by agents)

Hermes reads `STATE.md` for current context; appends a JSON line to `HISTORY.jsonl` on each phase transition.

**Cost:** Low. Convention change + ~10 lines of Hermes write logic.

**Worth it:** Yes. Also gives you the audit trail that's currently missing.

---

## Secondary Issues (not in top 3, but don't ignore)

- **No cost tracking.** Token spend per project is invisible. You'll overspend on RESEARCH (noisy cron) before you realize it. Add a `costs` section to `STATE.md` with cumulative estimates per phase.
- **RESEARCH has no quality gate.** Hermes scans HN/Reddit and categorises — but who validates the pain signal is real before you hit VALIDATE with users? You risk spending user-convo time on a false positive. Add a Hermes pre-screen: "Is there evidence of >3 distinct people describing this pain in the last 90 days? If not, abort."
- **No rollback definition.** If human rejects at VERIFY, what does "send back" mean? Back to EXECUTE? Back to PLAN? The loop is ambiguous on re-entry. Define it explicitly in the STATE.md schema.
- **Hermes runs terminal commands autonomously with no sandbox.** For greenfield projects this is fine. For anything touching production config or credentials, this is a supply chain risk. Not urgent, but flag it before you scale.

---

## Gate Compression Analysis

**Can you go from 3 gates to 2?** Yes, by merging VALIDATE + PLAN into a single gate: "I'm committing to build AND approving the direction simultaneously." This works if Claude generates the plan *before* VALIDATE, so you see architecture and user problem together. Downside: you do planning work on ideas you'll kill. For low-cost plans this is acceptable.

**Can you go to 1 gate?** Only at VERIFY. Cost: a bad plan runs to completion before you catch it. Realistic only if EXECUTE is cheap (small scope, fast tests). For anything > 2 days of agent work, the compounding error risk isn't worth it.

**Recommendation:** Stay at 3 gates until you have 10+ completed loops. You don't have enough data yet to know where the error rate is highest. Compress after you see where humans are rubber-stamping vs. actually catching problems.

---

## Big Swing — If Rebuilding From Scratch

**Make the loop self-modifying.**

The current design treats the loop as static infrastructure. Every completed project produces `STATE.md` + `HISTORY.jsonl` as artifacts that go nowhere. That's wasted signal.

The rebuild: after each COMMIT, Claude Code reviews `HISTORY.jsonl` for the completed project and proposes diffs to (a) the Hermes system prompt, and (b) the phase definitions in the loop spec. Hermes applies approved diffs. The loop rewrites itself.

After 20 projects, your Hermes prompts are calibrated to your domain, your test patterns, your common failure modes. After 50, you have a fine-tuning dataset no one can replicate without running those same 50 projects.

This is the moat. Not the loop design — anyone can copy a 7-phase diagram. The moat is **the accumulated prompt corpus** that emerges from running it. Build the logging infrastructure now (`HISTORY.jsonl`) so you can harvest it later.

---

## Execution Speed Reality Check

"Same day from plan to commit" is achievable **only if**:
- Scope < 500 LOC
- No external API discovery required
- Tests run in < 2 minutes
- Human is available within 2 hours for each gate

Realistic timeline for a real feature: 4-8 hours of agent-active time, spread over 1-2 days due to async gate latency. VALIDATE is not in this estimate — that's days, not hours, and it's the right call to keep it slow.

The actual bottleneck is not agent speed. It's **gate latency** (you being available) and **EXECUTE spinning on failing tests** without an exit condition (which is criticism #1 above).
