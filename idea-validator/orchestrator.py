"""
Orchestrator: manages the deliberation loop with per-agent conversation histories.
Agents maintain their own message arrays; the orchestrator passes stimuli between them.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, List

from agents import (
    Synthesizer, Skeptic, STAGE_NAMES,
    llm_extract_kill_conditions as extract_kill_conditions, format_kill_conditions, extract_objections,
    extract_synthesizer_ranking, extract_skeptic_ranking,
    strip_meta_commentary,
)
from momentum_tracker import MomentumTracker
from gate_manager import GateManager
from config import get_session_constraints
from tools import refresh_lead_counts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _append(transcript: List, role: str, stage: int, round_num: int, turn_type: str, content: str, claims: Dict = None):
    entry = {
        "role": role,
        "stage": stage,
        "round": round_num,
        "turn_type": turn_type,
        "content": content,
    }
    if claims:
        entry["claims"] = claims
    transcript.append(entry)


def _filter_kill_conditions(kill_conditions: List[Dict], approved_niche: str) -> List[Dict]:
    """Filter kill conditions at stage transitions.
    Mark conditions as inactive if they reference niches/pain points that were rejected.
    Only carry forward kill conditions that are relevant to the approved niche.
    """
    if not approved_niche:
        return kill_conditions
    
    niche_lower = approved_niche.lower()
    filtered = []
    
    # Keywords that strongly indicate a kill condition belongs to a specific niche
    # Map: keyword -> niche category it implies
    niche_specific_keywords = {
        "dvsa": "automotive",
        "mot": "automotive",
        "garage": "automotive",
        "vehicle": "automotive",
        "car dealer": "automotive",
        "hmrc": "tax",
        "mtd": "tax",
        "vat": "tax",
        "ioss": "ecom",
        "eori": "ecom",
        "marketplace": "ecom",
        "amazon": "ecom",
        "shopify": "ecom",
        "e-commerce": "ecom",
        "ecommerce": "ecom",
        "cis": "trades",
        "construction": "trades",
        "plumber": "trades",
        "beauty": "beauty_health",
        "salon": "beauty_health",
        "dentist": "beauty_health",
        "restaurant": "food_hospitality",
        "cafe": "food_hospitality",
    }
    
    for kc in kill_conditions:
        kc_text = kc.get("condition", "").lower()
        kc_copy = dict(kc)  # Shallow copy
        
        # Check if this KC is niche-specific and doesn't match our approved niche
        is_relevant = True
        matched_keywords = []
        for keyword, implied_niche in niche_specific_keywords.items():
            if keyword in kc_text:
                matched_keywords.append((keyword, implied_niche))
        
        if matched_keywords:
            # If ALL matched keywords point to a different niche category, mark inactive
            niche_categories = set(kw[1] for kw in matched_keywords)
            approved_category = None
            for keyword, implied_niche in niche_specific_keywords.items():
                if keyword in niche_lower:
                    approved_category = implied_niche
                    break
            
            if approved_category and approved_category not in niche_categories:
                # This KC references a rejected niche — mark inactive
                kc_copy["status"] = "inactive"
                kc_copy["reason"] = f"Niche changed to '{approved_niche}'; this condition references a rejected niche ({', '.join(niche_categories)})"
        
        filtered.append(kc_copy)
    
    return filtered


def _save_token_usage(session: Dict[str, Any], synthesizer: Synthesizer, skeptic: Skeptic, stage: int) -> None:
    """Capture token usage from both agents and append to session log."""
    synth_usage = synthesizer.client.get_usage_summary()
    sk_usage = skeptic.client.get_usage_summary()
    
    combined = {
        "stage": stage,
        "synthesizer": synth_usage,
        "skeptic": sk_usage,
        "total": {
            "prompt_tokens": synth_usage["prompt_tokens"] + sk_usage["prompt_tokens"],
            "completion_tokens": synth_usage["completion_tokens"] + sk_usage["completion_tokens"],
            "total_tokens": synth_usage["total_tokens"] + sk_usage["total_tokens"],
            "calls": synth_usage.get("calls", 0) + sk_usage.get("calls", 0),
        },
    }
    
    session.setdefault("token_usage", []).append(combined)
    
    t = combined["total"]
    print(f"\n📊 Stage {stage} token usage: {t['total_tokens']:,} tokens "
          f"({t['prompt_tokens']:,} prompt, {t['completion_tokens']:,} completion) "
          f"in {t['calls']} calls")
    
    # Reset for next stage
    synthesizer.client.reset_usage()
    skeptic.client.reset_usage()


def _skeptic_fully_convinced(skeptic_response: str) -> bool:
    """Check if the Skeptic has given all SURVIVE verdicts (no KILL or WEAK)."""
    upper = skeptic_response.upper()
    # Look for verdict keywords
    has_kill = "KILL" in upper
    has_weak = "WEAK" in upper
    has_survive = "SURVIVE" in upper
    # Fully convinced = at least one SURVIVE and no KILL/WEAK
    return has_survive and not has_kill and not has_weak


def _extract_unverified_for_skeptic(text: str) -> List[str]:
    """Extract [unverified]-tagged sentences from a single Synthesizer response.
    Returns up to 5 claims, each stripped to the sentence containing the tag.
    Used to build PRIORITY TARGETS block in Skeptic stimuli."""
    claims = []
    for m in re.finditer(r'\[unverified\]', text, re.IGNORECASE):
        start = text.rfind('.', 0, m.start()) + 1
        end = text.find('.', m.end())
        if end == -1:
            end = len(text)
        claim = text[start:end].strip()
        # Skip very short fragments or instruction echoes
        if len(claim) < 20 or any(p in claim.lower() for p in [
            "tag claims", "use the [unverified]", "unverified tag", "tag unverified",
            "claims as [unverified]", "mark as [unverified]",
        ]):
            continue
        # Strip the tag itself so the Skeptic sees the claim cleanly
        claim_clean = re.sub(r'\s*\[unverified\]', '', claim, flags=re.IGNORECASE).strip()
        if claim_clean and claim_clean not in claims:
            claims.append(claim_clean)
        if len(claims) >= 5:
            break
    return claims


def _build_priority_block(claims: List[str]) -> str:
    """Format extracted unverified claims as a PRIORITY TARGETS block."""
    if not claims:
        return ""
    lines = "\n".join(f"  - {c}" for c in claims)
    return f"\n\nPRIORITY TARGETS (unverified — attack these first):\n{lines}"


def _collect_unverified_claims(transcript: List[Dict], stage_filter: int) -> List[Dict]:
    """Scan transcript for [unverified] tagged claims in a given stage.
    Returns up to 5 claims, skipping instruction echoes and meta-reasoning."""
    claims = []
    instruction_echoes = [
        "tag unverified", "unverified claims", "i should", "i need to",
        "i must", "my job", "my instructions", "the user wants",
    ]
    meta_prefixes = [
        "i think", "i believe", "i feel", "in my opinion", "i would say",
    ]
    
    for entry in transcript:
        if entry.get("stage") != stage_filter:
            continue
        content = entry.get("content", "")
        # Find all [unverified] occurrences
        for match in re.finditer(r'([^\[\n]{10,200})\[unverified\]', content, re.IGNORECASE):
            claim_text = match.group(1).strip()
            lower_claim = claim_text.lower()
            
            # Skip instruction echoes
            if any(echo in lower_claim for echo in instruction_echoes):
                continue
            
            # Skip heavy first-person reasoning
            if any(prefix in lower_claim for prefix in meta_prefixes):
                continue
            
            # Skip very short claims
            if len(claim_text) < 15:
                continue
            
            claims.append({
                "claim": claim_text[:200],
                "source": f"{entry.get('role', '?')} round {entry.get('round', '?')}",
            })
            
            if len(claims) >= 5:
                return claims
    
    return claims


# ---------------------------------------------------------------------------
# Stage 1: Niche Alignment
# ---------------------------------------------------------------------------

# Stage 1: Niche Alignment
# ---------------------------------------------------------------------------

def run_stage1(session: Dict[str, Any], synthesizer: Synthesizer, skeptic: Skeptic) -> Dict[str, Any]:
    """Run Stage 1 deliberation. Agents may already be initialized (resume) or fresh."""
    manifest = session["manifest"]
    constraints = get_session_constraints(manifest)
    max_turns = constraints["max_turns"]
    max_pivots = constraints["max_pivots"]
    momentum = MomentumTracker()
    gate_manager = GateManager()

    transcript: List[Dict] = session.setdefault("transcript", [])

    # -------------------------------------------------------------------
    # Initialize agents if they have no history (fresh session)
    # -------------------------------------------------------------------
    # Refresh live lead counts from Supabase before Stage 1
    live_counts = refresh_lead_counts()
    
    context = {
        "manifest": manifest,
        "rejected_niches": manifest.get("ruled_out_niches", []),
        "required_evidence": manifest.get("required_evidence", []),
        "lead_counts": live_counts if live_counts else manifest.get("lead_segments", {}),
    }

    if not synthesizer.history:
        synthesizer.initialize(stage_num=1, context=context)
    if not skeptic.history:
        # Pass pivot_used flag from session to prevent double-pivoting
        skeptic.initialize(stage_num=1, context={**context, "pivot_used": session.get("pivot_used", False)})

    print(f"\n{'='*70}")
    print(f"  STAGE 1: {STAGE_NAMES[1]}")
    print(f"{'='*70}")

    # -------------------------------------------------------------------
    # Round 1: Synthesizer opens with niche proposals
    # -------------------------------------------------------------------
    print("\n[Synthesizer] Proposing niches...")
    synth_r1 = synthesizer.respond()  # No stimulus — uses the init user message

    # Extract kill conditions from Round 1 proposals
    proposed_kc = extract_kill_conditions(synth_r1)
    print(f"  Extracted {len(proposed_kc)} kill conditions from proposals.")
    for kc in proposed_kc:
        kc["status"] = "signed_off"
    signed_off = proposed_kc
    session["kill_conditions"] = signed_off
    context["kill_conditions"] = signed_off

    # Skeptic's first stimulus: proposal + kill conditions + technical constraints inline
    kc_text = format_kill_conditions(signed_off) if signed_off else ""
    tech_constraints = manifest.get("technical_constraints", [])
    constraints_text = ""
    if tech_constraints:
        constraints_text = "\nTechnical constraints to check against:\n" + "\n".join(f"  - {c}" for c in tech_constraints[:5])
    # Extract unverified claims from Synthesizer response for targeted Skeptic attacks
    unverified_r1 = _extract_unverified_for_skeptic(synth_r1)
    priority_block_r1 = _build_priority_block(unverified_r1)
    
    skeptic_stimulus = (
        f"The Synthesizer proposes these niches:\n\n{synth_r1}"
        + (f"\n\n{kc_text}" if kc_text else "")
        + constraints_text
        + priority_block_r1
        + "\n\nChallenge each niche. State SURVIVE, KILL, or WEAK for each with your sharpest objection."
    )
    sk_r1 = skeptic.respond(skeptic_stimulus)

    _append(transcript, "Synthesizer", 1, 1, "deliberation", synth_r1)
    _append(transcript, "Skeptic", 1, 1, "deliberation", sk_r1)

    # Track momentum from Skeptic's objections
    objections = extract_objections(sk_r1)
    momentum.record_turn(objections_raised=objections, objections_resolved=[])

    # -------------------------------------------------------------------
    # Early convergence exit: if Skeptic is fully convinced after Round 1,
    # skip remaining rounds and go straight to gate.
    # -------------------------------------------------------------------
    if _skeptic_fully_convinced(sk_r1):
        print("\n✅ Skeptic fully convinced (all SURVIVE). Skipping remaining rounds.")
        # Skip to convergence check
        sk_r2 = sk_r1
    else:
        # -------------------------------------------------------------------
        # Rounds 2+: stimulus passing
        # -------------------------------------------------------------------
        for round_num in range(2, max_turns + 1):
            print(f"\n{'='*70}")
            print(f"  ROUND {round_num}/{max_turns}")
            print(f"{'='*70}")

            # Synthesizer receives Skeptic's last challenge
            synth_stimulus = (
                f"The Skeptic challenges your niches. Here's their critique:\n\n{sk_r1}\n\n"
                f"Defend your niches where the Skeptic is wrong. Concede where they are right. "
                f"Propose refinements if needed. Keep the same 3 niches or explain why you must change one."
            )
            synth_r2 = synthesizer.respond(synth_stimulus)

            # Skeptic receives Synthesizer's defense
            # Extract any new unverified claims from the Synthesizer's refined response
            unverified_rN = _extract_unverified_for_skeptic(synth_r2)
            priority_block_rN = _build_priority_block(unverified_rN)
            
            sk_stimulus = (
                f"The Synthesizer responds to your challenges:\n\n{synth_r2}"
                + priority_block_rN
                + "\n\nContinue your challenge. Are you convinced, or do your objections still stand?"
            )
            sk_r2 = skeptic.respond(sk_stimulus)

            _append(transcript, "Synthesizer", 1, round_num, "deliberation", synth_r2)
            _append(transcript, "Skeptic", 1, round_num, "deliberation", sk_r2)

            # Track momentum
            objections = extract_objections(sk_r2)
            momentum.record_turn(objections_raised=objections, objections_resolved=[])

            # Check for pivot
            pivot_requested = "pivot" in sk_r2.lower() and "restart" in sk_r2.lower()
            if pivot_requested:
                if session.get("pivot_count", 0) < max_pivots:
                    print(f"\n🔄 Skeptic requests pivot. ({session.get('pivot_count',0)+1}/{max_pivots} used)")
                    session["pivot_count"] = session.get("pivot_count", 0) + 1
                    session["pivot_used"] = True  # Mark pivot as used for downstream stages
                    # Reset: Synthesizer proposes 3 new niches
                    reset_msg = (
                        f"The Skeptic demands a full pivot — 3 entirely new niches. "
                        f"Start fresh, grounded in the manifest data. Do not reuse previous niches."
                    )
                    synth_r1 = synthesizer.respond(reset_msg)
                    sk_r1 = skeptic.respond(
                        f"The Synthesizer proposes 3 new niches:\n\n{synth_r1}\n\nChallenge these."
                    )
                    _append(transcript, "Synthesizer", 1, round_num, "pivot", synth_r1)
                    _append(transcript, "Skeptic", 1, round_num, "pivot", sk_r1)
                    continue
                else:
                    print(f"\n⚠️ Pivot requested but budget exhausted ({max_pivots}/{max_pivots}).")

            # Adaptive break: check momentum health from Round 2 onwards.
            # If deadlocked or deteriorating, exit early. If converging strongly,
            # continue to next round.
            if round_num >= 2:
                if momentum.is_deadlocked():
                    print(f"\n⛔ DEADLOCK detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_deteriorating():
                    print(f"\n⛔ DETERIORATION detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_converging() and round_num >= 3:
                    print(f"\n✅ Strong convergence detected after Round {round_num}. Continuing.")

            sk_r1 = sk_r2  # Update reference for next round

    # -------------------------------------------------------------------
    # Convergence: transcript-based rankings (zero API calls)
    # Synthesizer ranking = order niches appeared in Round 1 proposal
    # Skeptic ranking = SURVIVE > WEAK > KILL from verdicts across all rounds
    # -------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  CONVERGENCE CHECK — Extracting rankings from transcript")
    print(f"{'='*70}")

    synth_ranking = extract_synthesizer_ranking(transcript)
    sk_ranking = extract_skeptic_ranking(transcript)
    print(f"\n  Synthesizer ranking: {synth_ranking}")
    print(f"  Skeptic ranking:     {sk_ranking}")

    # Determine convergence
    convergence_type = "disputed"
    if synth_ranking and sk_ranking:
        if synth_ranking == sk_ranking:
            convergence_type = "strong"
        elif len(synth_ranking) >= 2 and len(sk_ranking) >= 2 and synth_ranking[:2] == sk_ranking[:2]:
            convergence_type = "partial_top2"
        elif synth_ranking[0] == sk_ranking[0]:
            convergence_type = "partial_top1"

    print(f"\n  Convergence type: {convergence_type.upper()}")

    # Collect unverified claims (Stage 1 only)
    unverified = _collect_unverified_claims(transcript, stage_filter=1)

    # Build gate data
    # Extract raw proposal previews for human verification
    synth_r1_preview = ""
    sk_r1_preview = ""
    for entry in transcript:
        if entry.get("role") == "Synthesizer" and entry.get("stage") == 1 and entry.get("round") == 1:
            synth_r1_preview = entry.get("content", "")[:1500]
        if entry.get("role") == "Skeptic" and entry.get("stage") == 1 and entry.get("round") == 1:
            sk_r1_preview = entry.get("content", "")[:1500]

    gate_data = {
        "synthesizer_ranking": synth_ranking,
        "skeptic_ranking": sk_ranking,
        "convergence_type": convergence_type,
        "niches": {},  # TODO: extract from claims blocks
        "kill_conditions": signed_off,
        "rejected_niches": manifest.get("ruled_out_niches", []),
        "unverified_claims": unverified,
        "evidence_status": manifest.get("required_evidence", []),
        "momentum_summary": momentum.summary(),
        "transcript_summary": "See full session JSON for transcript.",
        "raw_synthesizer_r1": synth_r1_preview,
        "raw_skeptic_r1": sk_r1_preview,
    }

    # Compress histories before saving to prevent context window bloat
    synthesizer.compress_history(max_tokens=300)
    skeptic.compress_history(max_tokens=300)
    
    # Save agent histories into session
    session["agent_histories"] = {
        "synthesizer": synthesizer.serialize(),
        "skeptic": skeptic.serialize(),
    }

    _save_token_usage(session, synthesizer, skeptic, stage=1)

    return {
        "status": "gate",
        "stage": 1,
        "convergence_type": convergence_type,
        "gate_data": gate_data,
        "transcript": transcript,
    }


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def run_stage2(session: Dict[str, Any], synthesizer: Synthesizer, skeptic: Skeptic) -> Dict[str, Any]:
    """Run Stage 2: Pain Point Research.
    Uses web search + dual-agent deliberation to validate pain points
    for the Stage-1-approved niche."""
    from research import search_pain_points, format_search_results

    manifest = session["manifest"]
    constraints = get_session_constraints(manifest)
    max_turns = constraints["max_turns"]
    approved_niche = session.get("approved_niche", "")
    kill_conditions = _filter_kill_conditions(
        session.get("kill_conditions", []), approved_niche
    )
    session["kill_conditions"] = kill_conditions

    if not approved_niche:
        raise ValueError("No approved niche found in session. Stage 1 gate must be approved first.")

    print(f"\n{'='*70}")
    print(f"  STAGE 2: Pain Point Research")
    print(f"  Niche: {approved_niche}")
    print(f"{'='*70}")

    momentum = MomentumTracker()

    # -------------------------------------------------------------------
    # Web search: gather evidence about the niche's pain points
    # -------------------------------------------------------------------
    print("\n🔍 Searching web for pain point evidence...")
    search_results = search_pain_points(approved_niche)
    search_md = format_search_results(search_results)
    print(f"   Searches completed: {len(search_results)} categories")

    # -------------------------------------------------------------------
    # Initialize agents for Stage 2 (fresh histories)
    # -------------------------------------------------------------------
    # Synthesizer: system prompt only; Stage 2 user message is sent as stimulus
    # Skeptic: same as Stage 1 — system prompt only, first stimulus from orchestrator
    if not synthesizer.history:
        synthesizer.history = [
            {"role": "system", "content": "You are the SYNTHESIZER agent in a falsification engine. Your job is to find and rank the most painful, evidence-backed problems within a startup niche. Always cite sources. Tag unverified claims with [unverified]."},
        ]
    if not skeptic.history:
        skeptic.initialize(stage_num=2, context={"pivot_used": session.get("pivot_used", False)})

    transcript: List[Dict] = session.setdefault("transcript", [])

    # -------------------------------------------------------------------
    # Check if Stage 2 already exists in transcript (resume case)
    # -------------------------------------------------------------------
    existing_stage2 = [e for e in transcript if e.get("stage") == 2]
    if len(existing_stage2) >= 2:
        print(f"\n⚡ Stage 2 deliberation already found in transcript ({len(existing_stage2)} entries).")
        print("   Skipping agent deliberation — going straight to gate generation.")
        
        pain_points = extract_pain_points_from_transcript(transcript, niche_name=approved_niche)
        unverified = _collect_unverified_claims(transcript, stage_filter=2)
        
        gate_data = {
            "approved_niche": approved_niche,
            "pain_points": pain_points,
            "convergence_type": "disputed" if not pain_points else "partial",
            "kill_conditions": kill_conditions,
            "unverified_claims": unverified,
            "evidence_status": manifest.get("required_evidence", []),
            "transcript_summary": "See full session JSON for transcript.",
        }
        
        # Compress histories before saving to prevent context window bloat
        synthesizer.compress_history(max_tokens=300)
        skeptic.compress_history(max_tokens=300)
        
        # Save current agent histories (they may have been restored)
        session["agent_histories_stage2"] = {
            "synthesizer": synthesizer.serialize(),
            "skeptic": skeptic.serialize(),
        }
        
        return {
            "status": "gate",
            "stage": 2,
            "convergence_type": gate_data["convergence_type"],
            "gate_data": gate_data,
            "transcript": transcript,
        }

    # -------------------------------------------------------------------
    # Round 1: Synthesizer proposes pain points using web evidence
    # -------------------------------------------------------------------
    print("\n[Synthesizer] Proposing pain points...")
    stage2_init = (
        f"STAGE 2 — Pain Point Research\n\n"
        f"The human has approved this niche: {approved_niche}\n\n"
        f"Signed-off kill conditions:\n"
    )
    for kc in kill_conditions:
        stage2_init += f"  - {kc.get('id','kc')}: {kc.get('condition','')}\n"
    stage2_init += (
        f"\nWeb search evidence:\n{search_md}\n\n"
        f"Your job: propose the 3 most painful, specific, and evidence-backed problems "
        f"within this niche. For each pain point, cite the source URL or evidence snippet. "
        f"Use the [unverified] tag for any claim you cannot back with the search results. "
        f"Return your pain points in a clear ranked list."
    )
    synth_r1 = synthesizer.respond(stage2_init)

    # Skeptic challenges the evidence quality
    # Extract unverified claims for targeted attacks
    unverified_r1 = _extract_unverified_for_skeptic(synth_r1)
    priority_block_r1 = _build_priority_block(unverified_r1)
    
    skeptic_stimulus = (
        f"The Synthesizer proposes these pain points for niche '{approved_niche}':\n\n"
        f"{synth_r1}"
        + priority_block_r1
        + "\n\nChallenge each pain point. Is the evidence strong enough? Are there contradictory "
        "sources? Could the pain be solved by existing tools? State SURVIVE, WEAK, or KILL for each."
    )
    sk_r1 = skeptic.respond(skeptic_stimulus)

    _append(transcript, "Synthesizer", 2, 1, "deliberation", synth_r1)
    _append(transcript, "Skeptic", 2, 1, "deliberation", sk_r1)

    # Track momentum from Skeptic's objections
    objections = extract_objections(sk_r1)
    momentum.record_turn(objections_raised=objections, objections_resolved=[])

    # Early convergence exit
    if _skeptic_fully_convinced(sk_r1):
        print("\n✅ Skeptic fully convinced (all SURVIVE). Skipping remaining rounds.")
        sk_r2 = sk_r1
    else:
        # -------------------------------------------------------------------
        # Rounds 2+: stimulus passing (same pattern as Stage 1)
        # -------------------------------------------------------------------
        for round_num in range(2, max_turns + 1):
            print(f"\n{'='*70}")
            print(f"  ROUND {round_num}/{max_turns}")
            print(f"{'='*70}")

            synth_stimulus = (
                f"The Skeptic challenges your pain points. Here's their critique:\n\n{sk_r1}\n\n"
                f"Defend where the evidence is strong. Concede where the Skeptic is right. "
                f"Refine or replace weak pain points. Keep the same 3 pain points or explain why you must change one."
            )
            synth_r2 = synthesizer.respond(synth_stimulus)

            # Extract unverified claims from Synthesizer's refined response
            unverified_rN = _extract_unverified_for_skeptic(synth_r2)
            priority_block_rN = _build_priority_block(unverified_rN)
            
            sk_stimulus = (
                f"The Synthesizer responds to your challenges:\n\n{synth_r2}"
                + priority_block_rN
                + "\n\nContinue your challenge. Are you convinced, or do your objections still stand?"
            )
            sk_r2 = skeptic.respond(sk_stimulus)

            _append(transcript, "Synthesizer", 2, round_num, "deliberation", synth_r2)
            _append(transcript, "Skeptic", 2, round_num, "deliberation", sk_r2)

            # Track momentum
            objections = extract_objections(sk_r2)
            momentum.record_turn(objections_raised=objections, objections_resolved=[])

            # Adaptive break
            if round_num >= 2:
                if momentum.is_deadlocked():
                    print(f"\n⛔ DEADLOCK detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_deteriorating():
                    print(f"\n⛔ DETERIORATION detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_converging() and round_num >= 3:
                    print(f"\n✅ Strong convergence detected after Round {round_num}. Continuing.")

            sk_r1 = sk_r2

    # -------------------------------------------------------------------
    # Convergence: extract pain points from Synthesizer R1
    # -------------------------------------------------------------------
    print(f"\n{'='*70}")
    print(f"  CONVERGENCE CHECK — Extracting pain points from transcript")
    print(f"{'='*70}")

    # Extract pain point names from Synthesizer Round 1 (similar to niche extraction)
    pain_points = extract_pain_points_from_transcript(transcript, niche_name=approved_niche)
    print(f"\n  Pain points found: {pain_points}")

    # Collect unverified claims (Stage 2 only)
    unverified = _collect_unverified_claims(transcript, stage_filter=2)

    # Build gate data — include web search evidence for human verification
    gate_data = {
        "approved_niche": approved_niche,
        "pain_points": pain_points,
        "convergence_type": "disputed" if not pain_points else "partial",
        "kill_conditions": kill_conditions,
        "unverified_claims": unverified,
        "evidence_status": manifest.get("required_evidence", []),
        "transcript_summary": "See full session JSON for transcript.",
        "search_evidence": search_results,
    }

    # Compress histories before saving to prevent context window bloat
    synthesizer.compress_history(max_tokens=300)
    skeptic.compress_history(max_tokens=300)
    
    # Save agent histories into session
    session["agent_histories_stage2"] = {
        "synthesizer": synthesizer.serialize(),
        "skeptic": skeptic.serialize(),
    }

    _save_token_usage(session, synthesizer, skeptic, stage=2)

    return {
        "status": "gate",
        "stage": 2,
        "convergence_type": gate_data["convergence_type"],
        "gate_data": gate_data,
        "transcript": transcript,
    }


def run_stage3(session: Dict[str, Any], synthesizer: Synthesizer, skeptic: Skeptic) -> Dict[str, Any]:
    """Run Stage 3: Solution Design.
    Synthesizer proposes solutions to the approved pain point.
    Skeptic challenges feasibility against manifest constraints and kill conditions."""

    manifest = session["manifest"]
    constraints = get_session_constraints(manifest)
    max_turns = constraints["max_turns"]
    approved_niche = session.get("approved_niche", "")
    approved_pain_point = session.get("approved_pain_point", "")
    kill_conditions = _filter_kill_conditions(
        session.get("kill_conditions", []), approved_niche
    )
    session["kill_conditions"] = kill_conditions

    if not approved_niche or not approved_pain_point:
        raise ValueError("No approved niche/pain point found. Stage 1 and 2 gates must be approved first.")

    print(f"\n{'='*70}")
    print(f"  STAGE 3: Solution Design")
    print(f"  Niche: {approved_niche}")
    print(f"  Pain Point: {approved_pain_point}")
    print(f"{'='*70}")

    momentum = MomentumTracker()

    if not synthesizer.history:
        synthesizer.history = [
            {"role": "system", "content": "You are the SYNTHESIZER agent in a falsification engine. Your job is to design startup solutions. For each solution, define: name, core mechanism, technical feasibility, budget fit, and timeline fit. Tag unverified claims with [unverified]."},
        ]
    if not skeptic.history:
        skeptic.initialize(stage_num=3, context={"pivot_used": session.get("pivot_used", False)})

    transcript: List[Dict] = session.setdefault("transcript", [])

    # Round 1: Synthesizer proposes solutions
    print("\n[Synthesizer] Proposing solutions...")
    stage3_init = (
        f"STAGE 3 — Solution Design\n\n"
        f"The human has approved:\n"
        f"  - Niche: {approved_niche}\n"
        f"  - Pain Point: {approved_pain_point}\n\n"
        f"Signed-off kill conditions:\n"
    )
    for kc in kill_conditions:
        stage3_init += f"  - {kc.get('id','kc')}: {kc.get('condition','')}\n"
    stage3_init += (
        f"\nManifest constraints:\n"
        f"  - Monthly burn: £{manifest.get('budget_ceiling',{}).get('monthly_burn','?')}\n"
        f"  - Max CAC: £{manifest.get('budget_ceiling',{}).get('max_cac','?')}\n"
        f"  - Timeline: {manifest.get('timeline_months','?')} months\n"
        f"  - Technical constraints: {'; '.join(manifest.get('technical_constraints', [])[:3])}\n\n"
        f"Your job: propose 3 distinct solutions to the approved pain point. "
        f"For each solution: name, core mechanism, technical feasibility (high/medium/low), "
        f"estimated build time, estimated monthly cost, and alignment with manifest constraints. "
        f"Rank them 1–3. Tag unverified claims with [unverified]."
    )
    synth_r1 = synthesizer.respond(stage3_init)

    # Skeptic challenges feasibility
    # Extract unverified claims for targeted attacks
    unverified_r1 = _extract_unverified_for_skeptic(synth_r1)
    priority_block_r1 = _build_priority_block(unverified_r1)
    
    sk_stimulus = (
        f"The Synthesizer proposes these solutions for niche '{approved_niche}' and pain point '{approved_pain_point}':\n\n"
        f"{synth_r1}"
        + priority_block_r1
        + f"\n\nChallenge each solution. Check: Does it violate manifest constraints? "
        f"Is it technically feasible within {manifest.get('timeline_months','?')} months? "
        f"Does it respect the signed-off kill conditions? "
        f"State SURVIVE, WEAK, or KILL for each."
    )
    sk_r1 = skeptic.respond(sk_stimulus)

    _append(transcript, "Synthesizer", 3, 1, "deliberation", synth_r1)
    _append(transcript, "Skeptic", 3, 1, "deliberation", sk_r1)

    # Track momentum from Skeptic's objections
    objections = extract_objections(sk_r1)
    momentum.record_turn(objections_raised=objections, objections_resolved=[])

    # Early convergence exit
    if _skeptic_fully_convinced(sk_r1):
        print("\n✅ Skeptic fully convinced (all SURVIVE). Skipping remaining rounds.")
        sk_r2 = sk_r1
    else:
        # Rounds 2+: stimulus passing
        for round_num in range(2, max_turns + 1):
            print(f"\n{'='*70}")
            print(f"  ROUND {round_num}/{max_turns}")
            print(f"{'='*70}")

            synth_stimulus = (
                f"The Skeptic challenges your solutions. Here's their critique:\n\n{sk_r1}\n\n"
                f"Defend where the Skeptic is wrong. Concede where they are right. "
                f"Refine or replace weak solutions. Keep the same 3 solutions or explain why you must change one."
            )
            synth_r2 = synthesizer.respond(synth_stimulus)

            # Extract unverified claims from Synthesizer's refined response
            unverified_rN = _extract_unverified_for_skeptic(synth_r2)
            priority_block_rN = _build_priority_block(unverified_rN)
            
            sk_stimulus = (
                f"The Synthesizer responds to your challenges:\n\n{synth_r2}"
                + priority_block_rN
                + "\n\nContinue your challenge. Are you convinced, or do your objections still stand?"
            )
            sk_r2 = skeptic.respond(sk_stimulus)

            _append(transcript, "Synthesizer", 3, round_num, "deliberation", synth_r2)
            _append(transcript, "Skeptic", 3, round_num, "deliberation", sk_r2)

            # Track momentum
            objections = extract_objections(sk_r2)
            momentum.record_turn(objections_raised=objections, objections_resolved=[])

            # Adaptive break
            if round_num >= 2:
                if momentum.is_deadlocked():
                    print(f"\n⛔ DEADLOCK detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_deteriorating():
                    print(f"\n⛔ DETERIORATION detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_converging() and round_num >= 3:
                    print(f"\n✅ Strong convergence detected after Round {round_num}. Continuing.")

            sk_r1 = sk_r2

    # Convergence: extract solutions from Synthesizer Round 1
    print(f"\n{'='*70}")
    print(f"  CONVERGENCE CHECK — Extracting solutions from transcript")
    print(f"{'='*70}")

    solutions = extract_solutions_from_transcript(transcript)
    print(f"\n  Solutions found: {solutions}")

    unverified = _collect_unverified_claims(transcript, stage_filter=3)

    gate_data = {
        "approved_niche": approved_niche,
        "approved_pain_point": approved_pain_point,
        "solutions": solutions,
        "convergence_type": "disputed" if not solutions else "partial",
        "kill_conditions": kill_conditions,
        "unverified_claims": unverified,
        "evidence_status": manifest.get("required_evidence", []),
        "transcript_summary": "See full session JSON for transcript.",
    }

    # Compress histories before saving to prevent context window bloat
    synthesizer.compress_history(max_tokens=300)
    skeptic.compress_history(max_tokens=300)
    
    session["agent_histories_stage3"] = {
        "synthesizer": synthesizer.serialize(),
        "skeptic": skeptic.serialize(),
    }

    _save_token_usage(session, synthesizer, skeptic, stage=3)

    return {
        "status": "gate",
        "stage": 3,
        "convergence_type": gate_data["convergence_type"],
        "gate_data": gate_data,
        "transcript": transcript,
    }


def run_stage4(session: Dict[str, Any], synthesizer: Synthesizer, skeptic: Skeptic) -> Dict[str, Any]:
    """Run Stage 4: Business Model & Pricing.
    Synthesizer proposes pricing tiers and unit economics.
    Skeptic challenges feasibility, especially CAC thresholds (two-tier enforcement)."""
    from agents import llm_extract_pricing_tiers as extract_pricing_tiers, llm_extract_unit_economics as extract_unit_economics

    manifest = session["manifest"]
    constraints = get_session_constraints(manifest)
    max_turns = constraints["max_turns"]
    approved_niche = session.get("approved_niche", "")
    approved_pain_point = session.get("approved_pain_point", "")
    approved_solution = session.get("approved_solution", "")
    kill_conditions = _filter_kill_conditions(
        session.get("kill_conditions", []), approved_niche
    )
    session["kill_conditions"] = kill_conditions
    max_cac = manifest.get("budget_ceiling", {}).get("max_cac", 50)

    if not approved_niche or not approved_pain_point or not approved_solution:
        raise ValueError("No approved niche/pain point/solution found. Stages 1-3 gates must be approved first.")

    print(f"\n{'='*70}")
    print(f"  STAGE 4: Business Model & Pricing")
    print(f"  Niche: {approved_niche}")
    print(f"  Pain Point: {approved_pain_point}")
    print(f"  Solution: {approved_solution}")
    print(f"  Max CAC: £{max_cac}")
    print(f"{'='*70}")

    momentum = MomentumTracker()

    if not synthesizer.history:
        synthesizer.history = [
            {"role": "system", "content": "You are the SYNTHESIZER agent in a falsification engine. Your job is to design business models and pricing. Define: pricing tiers (3 tiers), unit economics (CAC, LTV, gross margin, payback period), and go-to-market assumptions. Tag unverified claims with [unverified]."},
        ]
    if not skeptic.history:
        skeptic.initialize(stage_num=4, context={"pivot_used": session.get("pivot_used", False)})

    transcript: List[Dict] = session.setdefault("transcript", [])

    # Round 1: Synthesizer proposes business model
    print("\n[Synthesizer] Proposing business model...")
    stage4_init = (
        f"STAGE 4 — Business Model & Pricing\n\n"
        f"The human has approved:\n"
        f"  - Niche: {approved_niche}\n"
        f"  - Pain Point: {approved_pain_point}\n"
        f"  - Solution: {approved_solution}\n\n"
        f"Signed-off kill conditions:\n"
    )
    for kc in kill_conditions:
        stage4_init += f"  - {kc.get('id','kc')}: {kc.get('condition','')}\n"
    stage4_init += (
        f"\nManifest constraints:\n"
        f"  - Monthly burn: £{manifest.get('budget_ceiling',{}).get('monthly_burn','?')}\n"
        f"  - Max CAC: £{max_cac} (two-tier: ≤£50 safe, £50-100 WEAK, >£100 auto-KILL)\n"
        f"  - Timeline: {manifest.get('timeline_months','?')} months\n"
        f"  - Technical constraints: {'; '.join(manifest.get('technical_constraints', [])[:3])}\n\n"
        f"Your job: propose a complete business model:\n"
        f"  1. Three pricing tiers (name, price, billing period, what it includes)\n"
        f"  2. Unit economics — you MUST provide all four:\n"
        f"     a. CAC (Customer Acquisition Cost)\n"
        f"     b. Monthly churn rate assumption (%). Be explicit: 'We assume X% monthly churn because...'\n"
        f"     c. LTV calculated from churn: LTV = (average_monthly_revenue_per_user) / (monthly_churn_rate)\n"
        f"     d. Gross margin % and CAC payback period (months)\n"
        f"  3. Go-to-market: primary channel, estimated conversion rate, first 100 customers timeline\n"
        f"Be specific with numbers. Tag unverified claims with [unverified].\n\n"
        f"IMPORTANT: LTV without a stated churn assumption is meaningless. You must state your churn assumption and show the LTV calculation."
    )
    synth_r1 = synthesizer.respond(stage4_init)

    # Skeptic challenges unit economics, especially CAC and churn assumption
    # Extract unverified claims for targeted attacks
    unverified_r1 = _extract_unverified_for_skeptic(synth_r1)
    priority_block_r1 = _build_priority_block(unverified_r1)
    
    sk_stimulus = (
        f"The Synthesizer proposes this business model for '{approved_solution}':\n\n"
        f"{synth_r1}"
        + priority_block_r1
        + f"\n\nChallenge every number. Check:\n"
        f"  - Is CAC ≤ £{max_cac}? If CAC > £100, this is an automatic KILL.\n"
        f"  - Did they state a monthly churn rate assumption? If not, LTV is unverifiable.\n"
        f"  - Is the churn assumption realistic for this niche? (B2B SaaS typically 3-7% annual = 0.25-0.6% monthly)\n"
        f"  - Is LTV/CAC ratio > 3 based on their stated churn?\n"
        f"  - Is gross margin realistic for a SaaS?\n"
        f"  - Is the payback period under 12 months?\n"
        f"  - Are the pricing tiers competitive vs. existing solutions?\n"
        f"State SURVIVE, WEAK, or KILL for the overall business model, and flag specific numbers."
    )
    sk_r1 = skeptic.respond(sk_stimulus)

    _append(transcript, "Synthesizer", 4, 1, "deliberation", synth_r1)
    _append(transcript, "Skeptic", 4, 1, "deliberation", sk_r1)

    # Track momentum from Skeptic's objections
    objections = extract_objections(sk_r1)
    momentum.record_turn(objections_raised=objections, objections_resolved=[])

    # Early convergence exit
    if _skeptic_fully_convinced(sk_r1):
        print("\n✅ Skeptic fully convinced (all SURVIVE). Skipping remaining rounds.")
        sk_r2 = sk_r1
    else:
        # Rounds 2+: stimulus passing
        for round_num in range(2, max_turns + 1):
            print(f"\n{'='*70}")
            print(f"  ROUND {round_num}/{max_turns}")
            print(f"{'='*70}")

            synth_stimulus = (
                f"The Skeptic challenges your business model. Here's their critique:\n\n"
                f"{sk_r1}\n\n"
                f"Defend where the Skeptic is wrong. Concede where they are right. "
                f"If CAC is too high, propose a cheaper acquisition channel or higher pricing. "
                f"Revise numbers with sources or clear assumptions."
            )
            synth_r2 = synthesizer.respond(synth_stimulus)

            # Extract unverified claims from Synthesizer's refined response
            unverified_rN = _extract_unverified_for_skeptic(synth_r2)
            priority_block_rN = _build_priority_block(unverified_rN)
            
            sk_stimulus = (
                f"The Synthesizer responds to your challenges:\n\n"
                f"{synth_r2}"
                + priority_block_rN
                + "\n\nContinue your challenge. Are the revised numbers credible? "
                "Does the business model still violate manifest constraints?"
            )
            sk_r2 = skeptic.respond(sk_stimulus)

            _append(transcript, "Synthesizer", 4, round_num, "deliberation", synth_r2)
            _append(transcript, "Skeptic", 4, round_num, "deliberation", sk_r2)

            # Track momentum
            objections = extract_objections(sk_r2)
            momentum.record_turn(objections_raised=objections, objections_resolved=[])

            # Adaptive break
            if round_num >= 2:
                if momentum.is_deadlocked():
                    print(f"\n⛔ DEADLOCK detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_deteriorating():
                    print(f"\n⛔ DETERIORATION detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_converging() and round_num >= 3:
                    print(f"\n✅ Strong convergence detected after Round {round_num}. Continuing.")

            sk_r1 = sk_r2

    # Convergence: extract pricing tiers and unit economics
    print(f"\n{'='*70}")
    print(f"  CONVERGENCE CHECK — Extracting business model from transcript")
    print(f"{'='*70}")

    synth_r1_clean = strip_meta_commentary(synth_r1)
    pricing_tiers = extract_pricing_tiers(synth_r1_clean)
    unit_economics = extract_unit_economics(synth_r1_clean)
    print(f"\n  Pricing tiers found: {len(pricing_tiers)}")
    for t in pricing_tiers:
        price_display = t.get("price_str", f"£{t.get('price', '?')}")
        print(f"    - {t['name']}: {price_display}/{t.get('period', 'month')}")
    if unit_economics["cac"] is not None:
        print(f"  Unit economics: CAC £{unit_economics['cac']:.0f} ({unit_economics['cac_tier']})")
        if unit_economics["ltv"] is not None:
            print(f"    LTV £{unit_economics['ltv']:.0f}, ratio {unit_economics['ltv']/unit_economics['cac']:.1f}")
        if unit_economics["gross_margin"] is not None:
            print(f"    Gross margin: {unit_economics['gross_margin']:.0f}%")

    # Apply two-tier CAC enforcement
    cac_kill_triggered = False
    if unit_economics["cac_tier"] == "kill":
        print(f"\n⛔ CAC KILL triggered: £{unit_economics['cac']:.0f} > £100")
        cac_kill_triggered = True

    unverified = _collect_unverified_claims(transcript, stage_filter=4)

    gate_data = {
        "approved_niche": approved_niche,
        "approved_pain_point": approved_pain_point,
        "approved_solution": approved_solution,
        "pricing_tiers": pricing_tiers,
        "unit_economics": unit_economics,
        "cac_tier": unit_economics.get("cac_tier"),
        "cac_kill_triggered": cac_kill_triggered,
        "convergence_type": "disputed" if cac_kill_triggered else ("partial" if pricing_tiers else "disputed"),
        "kill_conditions": kill_conditions,
        "unverified_claims": unverified,
        "evidence_status": manifest.get("required_evidence", []),
        "transcript_summary": "See full session JSON for transcript.",
    }

    # Compress histories before saving to prevent context window bloat
    synthesizer.compress_history(max_tokens=300)
    skeptic.compress_history(max_tokens=300)
    
    session["agent_histories_stage4"] = {
        "synthesizer": synthesizer.serialize(),
        "skeptic": skeptic.serialize(),
    }

    _save_token_usage(session, synthesizer, skeptic, stage=4)

    return {
        "status": "gate",
        "stage": 4,
        "convergence_type": gate_data["convergence_type"],
        "gate_data": gate_data,
        "transcript": transcript,
    }


def run_stage5(session: Dict[str, Any], synthesizer: Synthesizer, skeptic: Skeptic) -> Dict[str, Any]:
    """Run Stage 5: Validation Sprint Design.
    Synthesizer proposes experiments to test the approved business model.
    Skeptic challenges whether experiments actually de-risk the venture."""
    from agents import llm_extract_sprint_plan as extract_sprint_plan

    manifest = session["manifest"]
    constraints = get_session_constraints(manifest)
    max_turns = constraints["max_turns"]
    approved_niche = session.get("approved_niche", "")
    approved_pain_point = session.get("approved_pain_point", "")
    approved_solution = session.get("approved_solution", "")
    approved_business_model = session.get("approved_business_model", {})
    kill_conditions = _filter_kill_conditions(
        session.get("kill_conditions", []), approved_niche
    )
    session["kill_conditions"] = kill_conditions
    default_duration = manifest.get("validation_sprint_duration_days", 30)

    if not approved_niche or not approved_pain_point or not approved_solution:
        raise ValueError("No approved niche/pain point/solution found. Stages 1-4 gates must be approved first.")

    print(f"\n{'='*70}")
    print(f"  STAGE 5: Validation Sprint Design")
    print(f"  Niche: {approved_niche}")
    print(f"  Solution: {approved_solution}")
    print(f"  Sprint Duration: {default_duration} days")
    print(f"{'='*70}")

    momentum = MomentumTracker()

    if not synthesizer.history:
        synthesizer.history = [
            {"role": "system", "content": "You are the SYNTHESIZER agent in a falsification engine. Your job is to design lean validation sprints. For each experiment: hypothesis, metric, success criteria, duration, and effort estimate. Tag unverified claims with [unverified]. Focus on experiments that can kill the idea, not just confirm it."},
        ]
    if not skeptic.history:
        skeptic.initialize(stage_num=5, context={"pivot_used": session.get("pivot_used", False)})

    transcript: List[Dict] = session.setdefault("transcript", [])

    # Resume guard: if Stage 5 deliberation already exists, skip to gate generation
    existing_stage5 = [e for e in transcript if e.get("stage") == 5]
    if len(existing_stage5) >= 2:
        print(f"\n⚡ Stage 5 deliberation already found in transcript ({len(existing_stage5)} entries).")
        print("   Skipping agent deliberation — going straight to gate generation.")

        from agents import llm_extract_sprint_plan as extract_sprint_plan
        stage5_synth_r1 = next(
            (e["content"] for e in existing_stage5
             if e.get("role") == "Synthesizer" and e.get("round") == 1),
            ""
        )
        experiments = extract_sprint_plan(stage5_synth_r1)
        unverified = _collect_unverified_claims(transcript, stage_filter=5)

        gate_data = {
            "approved_niche": approved_niche,
            "approved_pain_point": approved_pain_point,
            "approved_solution": approved_solution,
            "approved_business_model": approved_business_model,
            "experiments": experiments,
            "sprint_duration_days": default_duration,
            "convergence_type": "disputed" if not experiments else "partial",
            "kill_conditions": kill_conditions,
            "unverified_claims": unverified,
            "evidence_status": manifest.get("required_evidence", []),
            "transcript_summary": "See full session JSON for transcript.",
        }

        session["agent_histories_stage5"] = {
            "synthesizer": synthesizer.serialize(),
            "skeptic": skeptic.serialize(),
        }

        return {
            "status": "gate",
            "stage": 5,
            "convergence_type": gate_data["convergence_type"],
            "gate_data": gate_data,
            "transcript": transcript,
        }

    # Round 1: Synthesizer proposes validation experiments
    print("\n[Synthesizer] Proposing validation experiments...")
    stage5_init = (
        f"STAGE 5 — Validation Sprint Design\n\n"
        f"The human has approved:\n"
        f"  - Niche: {approved_niche}\n"
        f"  - Pain Point: {approved_pain_point}\n"
        f"  - Solution: {approved_solution}\n"
    )
    if approved_business_model:
        pricing = approved_business_model.get("pricing_tiers", [])
        ue = approved_business_model.get("unit_economics", {})
        if pricing:
            top = pricing[0]
            price_display = top.get("price_str", f"£{top.get('price', '?')}")
            stage5_init += f"  - Pricing: {len(pricing)} tiers (top: {top['name']} @ {price_display}/{top.get('period', 'month')})\n"
        if ue.get("cac") is not None:
            stage5_init += f"  - CAC: £{ue['cac']:.0f} ({ue.get('cac_tier','?')})\n"
        if ue.get("ltv") is not None:
            stage5_init += f"  - LTV: £{ue['ltv']:.0f}\n"
    stage5_init += (
        f"\nSigned-off kill conditions:\n"
    )
    for kc in kill_conditions:
        stage5_init += f"  - {kc.get('id','kc')}: {kc.get('condition','')}\n"
    stage5_init += (
        f"\nYour job: design a {default_duration}-day validation sprint with 3-5 experiments. "
        f"Each experiment must:\n"
        f"  1. Have a clear falsifiable hypothesis (what would KILL this idea?)\n"
        f"  2. Define a metric and success threshold\n"
        f"  3. Specify duration (within {default_duration} days total)\n"
        f"  4. Estimate effort (hours or £)\n"
        f"At least one experiment must directly test the top kill condition. "
        f"Order experiments by risk: highest-risk (most likely to kill) first."
    )
    synth_r1 = synthesizer.respond(stage5_init)

    # Skeptic challenges experiment design
    # Extract unverified claims for targeted attacks
    unverified_r1 = _extract_unverified_for_skeptic(synth_r1)
    priority_block_r1 = _build_priority_block(unverified_r1)
    
    sk_stimulus = (
        f"The Synthesizer proposes these validation experiments for '{approved_solution}':\n\n"
        f"{synth_r1}"
        + priority_block_r1
        + f"\n\nChallenge each experiment:\n"
        f"  - Does it actually test a core assumption, or is it just confirmation bias?\n"
        f"  - Is the success criterion falsifiable, or is it vague enough to always pass?\n"
        f"  - Can it be done within {default_duration} days and the manifest budget?\n"
        f"  - Will a 'success' actually de-risk the venture, or just feel good?\n"
        f"State SURVIVE, WEAK, or KILL for each experiment."
    )
    sk_r1 = skeptic.respond(sk_stimulus)

    _append(transcript, "Synthesizer", 5, 1, "deliberation", synth_r1)
    _append(transcript, "Skeptic", 5, 1, "deliberation", sk_r1)

    # Track momentum from Skeptic's objections
    objections = extract_objections(sk_r1)
    momentum.record_turn(objections_raised=objections, objections_resolved=[])

    # Early convergence exit
    if _skeptic_fully_convinced(sk_r1):
        print("\n✅ Skeptic fully convinced (all SURVIVE). Skipping remaining rounds.")
        sk_r2 = sk_r1
    else:
        # Rounds 2+: stimulus passing
        for round_num in range(2, max_turns + 1):
            print(f"\n{'='*70}")
            print(f"  ROUND {round_num}/{max_turns}")
            print(f"{'='*70}")

            synth_stimulus = (
                f"The Skeptic challenges your validation experiments. Here's their critique:\n\n"
                f"{sk_r1}\n\n"
                f"Defend experiments that are sound. Replace weak ones with stronger tests. "
                f"Ensure at least one experiment is designed to KILL the idea if it fails. "
                f"Keep the total sprint within {default_duration} days."
            )
            synth_r2 = synthesizer.respond(synth_stimulus)

            # Extract unverified claims from Synthesizer's refined response
            unverified_rN = _extract_unverified_for_skeptic(synth_r2)
            priority_block_rN = _build_priority_block(unverified_rN)
            
            sk_stimulus = (
                f"The Synthesizer responds to your challenges:\n\n"
                f"{synth_r2}"
                + priority_block_rN
                + "\n\nContinue your challenge. Are the revised experiments truly falsifiable? "
                "Does the sprint order make sense (highest risk first)?"
            )
            sk_r2 = skeptic.respond(sk_stimulus)

            _append(transcript, "Synthesizer", 5, round_num, "deliberation", synth_r2)
            _append(transcript, "Skeptic", 5, round_num, "deliberation", sk_r2)

            # Track momentum
            objections = extract_objections(sk_r2)
            momentum.record_turn(objections_raised=objections, objections_resolved=[])

            # Adaptive break
            if round_num >= 2:
                if momentum.is_deadlocked():
                    print(f"\n⛔ DEADLOCK detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_deteriorating():
                    print(f"\n⛔ DETERIORATION detected after Round {round_num}. Escalating to human gate.")
                    break
                if momentum.is_converging() and round_num >= 3:
                    print(f"\n✅ Strong convergence detected after Round {round_num}. Continuing.")

            sk_r1 = sk_r2

    # Convergence: extract sprint plan
    print(f"\n{'='*70}")
    print(f"  CONVERGENCE CHECK — Extracting validation experiments")
    print(f"{'='*70}")

    experiments = extract_sprint_plan(synth_r1)
    print(f"\n  Experiments found: {len(experiments)}")
    for i, exp in enumerate(experiments, 1):
        print(f"    {i}. {exp['name'][:60]} ({exp['duration'] or 'no duration'})")

    unverified = _collect_unverified_claims(transcript, stage_filter=5)

    gate_data = {
        "approved_niche": approved_niche,
        "approved_pain_point": approved_pain_point,
        "approved_solution": approved_solution,
        "approved_business_model": approved_business_model,
        "experiments": experiments,
        "sprint_duration_days": default_duration,
        "convergence_type": "disputed" if not experiments else "partial",
        "kill_conditions": kill_conditions,
        "unverified_claims": unverified,
        "evidence_status": manifest.get("required_evidence", []),
        "transcript_summary": "See full session JSON for transcript.",
    }

    # Compress histories before saving to prevent context window bloat
    synthesizer.compress_history(max_tokens=300)
    skeptic.compress_history(max_tokens=300)
    
    session["agent_histories_stage5"] = {
        "synthesizer": synthesizer.serialize(),
        "skeptic": skeptic.serialize(),
    }

    _save_token_usage(session, synthesizer, skeptic, stage=5)

    return {
        "status": "gate",
        "stage": 5,
        "convergence_type": gate_data["convergence_type"],
        "gate_data": gate_data,
        "transcript": transcript,
    }


def generate_final_report(session: Dict[str, Any]) -> str:
    """Generate the final consolidated startup validation report.
    Compiles all approved decisions from Stages 1-5 into a single markdown document."""
    from datetime import datetime
    
    manifest = session.get("manifest", {})
    approved_niche = session.get("approved_niche", "")
    approved_pain_point = session.get("approved_pain_point", "")
    approved_solution = session.get("approved_solution", "")
    approved_business_model = session.get("approved_business_model", {})
    kill_conditions = session.get("kill_conditions", [])
    
    # Collect experiment data from approved_sprint first (clean), fallback to Stage 5 gate data
    approved_sprint = session.get("approved_sprint", {})
    experiments = approved_sprint.get("experiments", [])
    sprint_duration = approved_sprint.get("sprint_duration_days", 30)
    if not experiments:
        stage5 = session.get("stages", {}).get("5", {})
        gate_data = stage5.get("gate_data", {})
        experiments = gate_data.get("experiments", [])
        sprint_duration = gate_data.get("sprint_duration_days", 30)
    
    # Decision status
    stages_completed = sum(1 for s in [1,2,3,4,5] if str(s) in session.get("stages", {}))
    has_kill_condition_hit = any(
        kc.get("status") in ("active", "triggered", "hit") for kc in kill_conditions
    )
    
    report = f"""# Startup Validation Report
**Session:** {session.get("session_id", "unknown")}
**Generated:** {datetime.now().isoformat()}
**Stages Completed:** {stages_completed}/5
**Status:** {'⚠️ KILL CONDITION HIT' if has_kill_condition_hit else '✅ ALL GATES PASSED'}

---

## Executive Summary

| Stage | Decision | Artifact |
|-------|----------|----------|
| 1. Niche Alignment | APPROVED | **{approved_niche[:80]}** |
| 2. Pain Point Research | APPROVED | **{approved_pain_point[:80] if approved_pain_point else '—'}** |
| 3. Solution Design | APPROVED | **{approved_solution[:80] if approved_solution else '—'}** |
| 4. Business Model | APPROVED | {len(approved_business_model.get('pricing_tiers', []))} tiers |
| 5. Validation Sprint | APPROVED | {len(experiments)} experiments |

---

## Approved Niche

**{approved_niche}**

---

## Approved Pain Point

**{approved_pain_point}**

---

## Approved Solution

**{approved_solution}**

---

## Business Model Summary

### Pricing Tiers

"""
    
    pricing = approved_business_model.get("pricing_tiers", [])
    if pricing:
        for tier in pricing:
            price_display = tier.get("price_str", f"£{tier.get('price', '?')}")
            report += f"- **{tier['name']}**: {price_display}/{tier.get('period', 'month')}\n"
    else:
        report += "_(No pricing tiers recorded)_\n"
    
    report += "\n### Unit Economics\n\n"
    ue = approved_business_model.get("unit_economics", {})
    if ue.get("cac") is not None:
        tier_label = {"safe": "✅", "weak": "⚠️", "kill": "⛔"}.get(ue.get("cac_tier"), "?")
        report += f"- **CAC**: £{ue['cac']:.0f} {tier_label}\n"
    if ue.get("ltv") is not None:
        report += f"- **LTV**: £{ue['ltv']:.0f}\n"
    if ue.get("gross_margin") is not None:
        gm_pct = ue['gross_margin'] * 100 if ue['gross_margin'] < 1 else ue['gross_margin']
        report += f"- **Gross Margin**: {gm_pct:.0f}%\n"
    if ue.get("payback_months") is not None:
        report += f"- **Payback Period**: {ue['payback_months']:.1f} months\n"
    if ue.get("cac") and ue.get("ltv"):
        report += f"- **LTV/CAC Ratio**: {ue['ltv']/ue['cac']:.1f}x\n"
    
    report += f"""
---

## Validation Sprint

**Duration**: {sprint_duration} days

### Experiments

"""
    
    if experiments:
        for i, exp in enumerate(experiments, 1):
            report += f"""#### {i}. {exp['name']}
- **Hypothesis**: {exp['hypothesis'] or '—'}
- **Metric**: {exp['metric'] or '—'}
- **Success Criteria**: {exp['success_criteria'] or '—'}
- **Duration**: {exp['duration'] or '—'}

"""
    else:
        report += "_(No experiments recorded)_\n"
    
    report += f"""
---

## Kill Conditions (Still Active)

"""
    active_kc = [kc for kc in kill_conditions if kc.get("status") in ("active", "signed_off", "proposed")]
    if active_kc:
        for kc in active_kc:
            report += f"- **{kc.get('id', '?')}**: {kc.get('condition', '?')}\n"
    else:
        report += "_(No active kill conditions)_\n"
    
    # Token usage summary
    token_usage = session.get("token_usage", [])
    if token_usage:
        report += "\n## Token Usage\n\n"
        report += "| Stage | Prompt | Completion | Total | Calls |\n"
        report += "|-------|--------|------------|-------|-------|\n"
        total_prompt = total_completion = total_tokens = total_calls = 0
        for entry in token_usage:
            t = entry.get("total", {})
            report += f"| {entry.get('stage', '?')} | {t.get('prompt_tokens', 0):,} | {t.get('completion_tokens', 0):,} | {t.get('total_tokens', 0):,} | {t.get('calls', 0)} |\n"
            total_prompt += t.get("prompt_tokens", 0)
            total_completion += t.get("completion_tokens", 0)
            total_tokens += t.get("total_tokens", 0)
            total_calls += t.get("calls", 0)
        report += f"| **Total** | **{total_prompt:,}** | **{total_completion:,}** | **{total_tokens:,}** | **{total_calls}** |\n"
        report += "\n"
    
    report += f"""
---

## Next Steps

1. Execute the validation sprint experiments above
2. Measure against the defined success criteria
3. Re-convene for a Stage 5 review gate after sprint completion
4. If all kill conditions survive: proceed to build

---

*This report was generated by the falsification engine deliberation pipeline.*
*All decisions required human approval at each stage gate.*
"""
    
    return report


def extract_solutions_from_transcript(transcript: List[Dict]) -> List[Dict]:
    """Extract solution names from Stage 3 Synthesizer Round 1.
    Kimi K2.6 often describes solutions in free-form narrative rather than strict
    **Rank 1: Title** format. We use multiple patterns plus a narrative fallback.
    """
    names: List[str] = []
    seen = set()
    skip_phrases = {
        "why it", "how it", "the most", "evidence", "source", "conclusion",
        "summary", "stage", "niche", "pain point", "ranked by", "here are",
        "solution", "technical feasibility", "estimated", "alignment",
        "the synthesizer", "the skeptic", "my job", "my instructions",
        "i need to", "i must", "the user wants",
    }
    for entry in transcript:
        if entry.get("role") != "Synthesizer" or entry.get("stage") != 3 or entry.get("round") != 1:
            continue
        text = strip_meta_commentary(entry.get("content", ""))

        def _add_match(name: str) -> bool:
            name = name.strip().strip('*').strip()
            lower = name.lower()
            if len(name) < 15:
                return False
            if any(sp in lower for sp in skip_phrases):
                return False
            if lower in seen:
                return False
            # Don't accept purely first-person reasoning
            if lower.startswith(("i ", "my ", "let me", "so i", "now i")):
                return False
            seen.add(lower)
            # Truncate to first sentence for readability, but keep more if it's a short sentence
            first_sentence = re.split(r'[.!?]\s+', name)[0]
            if len(first_sentence) > 10:
                names.append(first_sentence[:150])
                return True
            return False

        # Pattern A: **Rank 1: Title** or **1. Title**
        for m in re.finditer(
            r'\*\*(?:[Rr]ank\s+)?(?:\d+[\.\):])?\s*([A-Z][^*\n]{15,150})\*\*',
            text,
        ):
            _add_match(m.group(1))

        # Pattern B: ### Rank 1: Title or ### 1. Title
        for m in re.finditer(
            r'(?:^|\n)\s*#{1,3}\s+(?:[Rr]ank\s+)?\d+[\.\):]\s+([A-Z][^\n#*]{20,200}?)\s*(?=\n\s*(?:#{1,3}|\*\*|$))',
            text,
        ):
            _add_match(m.group(1))

        # Pattern C: 1. **Title**
        for m in re.finditer(r'(?:^|\n)\s*\d+[\.\)]\s+\*\*([^*\n]{15,150})\*\*', text):
            _add_match(m.group(1))

        # Pattern D: "Solution 1: Name" or "Proposal 1: Name"
        for m in re.finditer(
            r'(?:^|\n)\s*(?:[Ss]olution|[Pp]roposal)\s*\d+[:.\s]+([A-Z][^\n*]{15,150})(?=\n|\*|$)',
            text,
        ):
            _add_match(m.group(1))

        # Pattern E: Narrative fallback — "**Name** — description" on its own line
        for m in re.finditer(
            r'(?:^|\n)\s*\*\*([^*\n]{10,120})\*\*\s*(?:[–—-]|:)\s*(?:high|medium|low|feasible|not feasible)',
            text,
            re.IGNORECASE,
        ):
            _add_match(m.group(1))

        # Pattern F: Broad narrative fallback — bold phrases that look like product names
        # (only if we still have < 2 matches — avoids over-extraction)
        if len(names) < 2:
            for m in re.finditer(
                r'(?:^|\n)(?:\s*\d+[\.\)]\s+)?\*\*([^*\n]{15,100})\*\*',
                text,
            ):
                candidate = m.group(1).strip()
                # Extra validation: must contain at least 2 content words (not just "Solution A")
                content_words = [w for w in candidate.split() if len(w) > 3 and w.lower() not in {
                    "solution", "proposal", "option", "idea", "concept", "approach", "strategy",
                }]
                if len(content_words) >= 2:
                    _add_match(candidate)
                if len(names) >= 3:
                    break

        # Pattern G: Ultimate fallback — first 3 sentences starting with capital letters
        # that contain a verb-like phrase ("for", "that", "with", "via") suggesting a mechanism
        if len(names) < 1:
            for line in text.split('\n'):
                line = line.strip()
                if line.startswith(("- ", "* ", "• ", "1. ", "2. ", "3. ")):
                    # Remove list marker
                    line = re.sub(r'^\s*[\*\-\•\d\.\)]\s+', '', line)
                if len(line) > 20 and len(line) < 200 and line[0].isupper():
                    # Check for mechanism words
                    mechanism_words = [" for ", " that ", " with ", " via ", " using ", " through ", " integrating ", " automating "]
                    if any(mw in line.lower() for mw in mechanism_words):
                        _add_match(line)
                if len(names) >= 3:
                    break

        break
    return [{"name": n, "status": "proposed"} for n in names[:3]]


def extract_pain_points_from_transcript(transcript: List[Dict], niche_name: str = "") -> List[Dict]:
    """Extract pain point names and evidence from Stage 2 Synthesizer Round 1.
    
    Expected format:
      ### 1. [Full sentence describing pain point]
      **Why it's the most painful:** [Explanation]
      
    Extracts the sentence after the number, not headers or explanations."""
    names: List[str] = []
    seen = set()
    skip_phrases = {
        "why it", "how it", "the most", "evidence", "source", "conclusion",
        "summary", "stage", "niche", "pain point", "ranked by", "here are",
        "digital patch test",  # matches the niche name
        "competitor reviews", "competitor landscape", "pain signals",
    }
    niche_lower = niche_name.lower()
    
    for entry in transcript:
        if entry.get("role") != "Synthesizer" or entry.get("stage") != 2 or entry.get("round") != 1:
            continue
        text = strip_meta_commentary(entry.get("content", ""))
        
        def _add_match(name: str) -> bool:
            """Add a pain point name if it passes filters. Returns True if added."""
            name = name.strip().strip('*').strip()
            lower = name.lower()
            if len(name) < 20:
                return False
            if any(sp in lower for sp in skip_phrases):
                return False
            if niche_lower and len(niche_lower) > 10 and niche_lower[:30] in lower:
                return False
            if lower in seen:
                return False
            seen.add(lower)
            # Truncate to first sentence for readability
            first_sentence = re.split(r'[.!?]\s+', name)[0]
            if len(first_sentence) > 15:
                names.append(first_sentence[:120])
                return True
            return False

        # Pattern A (highest priority): **Rank 1: Title** or **1. Title**
        for m in re.finditer(
            r'\*\*(?:[Rr]ank\s+)?(?:\d+[\.\):])?\s*([A-Z][^*\n]{15,150})\*\*',
            text,
        ):
            _add_match(m.group(1))

        # Pattern B: ### Rank 1: Title or ### 1. Title
        for m in re.finditer(
            r'(?:^|\n)\s*#{1,3}\s+(?:[Rr]ank\s+)?\d+[\.\):]\s+([A-Z][^\n#*]{20,200}?)\s*(?=\n\s*(?:#{1,3}|\*\*|$))',
            text,
        ):
            _add_match(m.group(1))

        # Pattern C: 1. **Pain point** — extract just the bold text
        for m in re.finditer(r'(?:^|\n)\s*\d+[\.\)]\s+\*\*([^*\n]{15,150})\*\*', text):
            _add_match(m.group(1))

        # Pattern D: 1. [Pain point] — fallback for non-bold numbered items
        if len(names) < 3:
            for m in re.finditer(r'(?:^|\n)\s*\d+[\.\)]\s+([A-Z][^\n]{20,200})', text):
                _add_match(m.group(1))

        break
    return [{"name": n, "status": "proposed"} for n in names[:3]]


def create_session(manifest: Dict[str, Any], niche_hint: str = "") -> Dict[str, Any]:
    from datetime import datetime
    session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {
        "session_id": session_id,
        "manifest": manifest,
        "niche_hint": niche_hint,
        "created_at": datetime.now().isoformat(),
        "current_stage": 1,
        "pivot_count": 0,
        "pivot_used": False,
        "kill_conditions": [],
        "stages": {},
        "transcript": [],
        "agent_histories": {},
    }


def save_session(session: Dict[str, Any]):
    import os
    from config import SESSIONS_DIR
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    path = os.path.join(SESSIONS_DIR, f"{session['session_id']}.json")
    with open(path, "w") as f:
        json.dump(session, f, indent=2, default=str)
    print(f"\n💾 Session saved: {path}")


def load_session(session_id: str) -> Dict[str, Any]:
    import os
    from config import SESSIONS_DIR
    path = os.path.join(SESSIONS_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Session not found: {path}")
    with open(path) as f:
        return json.load(f)


def list_sessions():
    import os
    from config import SESSIONS_DIR
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    files = sorted([f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")], reverse=True)
    if not files:
        print("No sessions found.")
        return
    print("Available sessions:")
    for f in files:
        sid = f[:-5]
        path = os.path.join(SESSIONS_DIR, f)
        with open(path) as fp:
            data = json.load(fp)
        stage = data.get("current_stage", "?")
        hint = data.get("niche_hint", "no hint")
        created = data.get("created_at", "")[:10]
        print(f"  {sid}  |  {hint}  |  stage {stage}  |  {created}")
