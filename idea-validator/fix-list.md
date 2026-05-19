## Fix List (COMPLETED)

**Fix #1: Momentum tracker `objections_resolved` always `[]`**
- ✅ `MomentumTracker._compute_resolved()` now compares previous round objections against current round using topic word overlap (first 4 significant words).
- Health score now meaningful (was always -1.0).

**Fix #2: `_inject_synthesize_summary()` doesn't pass `approved_solution_name`**
- ✅ Now passes `approved_solution_name` into context, enabling solution-aware prompts in Stage 4+.

**Fix #3: Kill conditions from rejected niches still appear in gate docs**
- ✅ `_filter_kill_conditions()` marks conditions referencing rejected niches as `inactive` at stage transitions.
- 2 of 5 original conditions now correctly marked inactive for ecom niche.

**Fix #4: Session history growing unbounded between stages**
- ✅ `compress_history()` added to both Synthesizer and Skeptic classes.
- Compresses full conversation to system prompt + 200-word summary before saving.
- Wired into orchestrator before every `agent_histories_stage{N}` save.
- Prevents Stage 5 double-run context window overflow.

**Fix #5: Skeptic can request multiple pivots across stages**
- ✅ `pivot_used` flag added to Skeptic class.
- Passed into Skeptic.initialize() context for all stages 1-5.
- Persisted to session when pivot detected (`session["pivot_used"] = True`).
- Restored from session when resuming (`skeptic.pivot_used = session.get("pivot_used", False)`).
- System prompt injects "PIVOT ALREADY USED" constraint when flag is set.
- Session initialization includes `"pivot_used": False`.

**Fix #6: Adaptive break after Round 2**
- ✅ Already implemented in orchestrator lines 356-365.
- `momentum.is_deadlocked()` → immediate gate escalation.
- `momentum.is_deteriorating()` → immediate gate escalation.
- `momentum.is_converging()` after Round 3 → continue with confidence.

## Next Steps
- Test the full pipeline with compression + pivot enforcement
- Monitor token usage in next live run to verify Stage 5 stays under budget
- Add unit tests for `compress_history()` and `pivot_used` flag behavior

## Summary of Changes
- `agents.py`: Added `compress_history()` to Synthesizer (line 815) and Skeptic (line 960); added `pivot_used` flag to Skeptic.__init__ and initialize(); system prompt injection for pivot constraint.
- `orchestrator.py`: Added `compress_history()` calls before all 5 stage history saves; added `pivot_used` to session init; wired `pivot_used` into all Skeptic.initialize() calls.
- `main.py`: Restores `skeptic.pivot_used` from session when resuming any stage.
