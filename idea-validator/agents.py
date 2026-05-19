"""
Agent definitions for the falsification engine.
Both agents are Kimi K2.6 (same model, different prompts).
Each agent maintains its own conversation history (OpenAI message format).
"""

import json
import re
import httpx
from typing import List, Dict, Any, Optional
from openai import OpenAI
from config import FIREWORKS_API_KEY, FIREWORKS_BASE_URL, KIMI_MODEL


# ---------------------------------------------------------------------------
# Regex extraction helpers (zero API calls)
# ---------------------------------------------------------------------------

def extract_niche_names(text: str) -> List[str]:
    """Extract niche names from Kimi's natural language output.
    Only matches lines that explicitly introduce a niche — no free-text capture.
    """
    text = strip_meta_commentary(text)
    seen, names = set(), []

    def _is_valid_name(name: str, seen: set) -> bool:
        lower = name.lower().strip()
        if not name or len(name) < 3 or lower in seen:
            return False
        # Reject instruction fragments and kill conditions
        bad_fragments = [
            "if ", "kill condition", "segment", "manifest", "the user", "let me",
            "i need", "i must", "my job", "my instructions", "niche is dead",
            "x is false", "actually ", "name:", "candidate", "revenue", "pain:",
        ]
        if any(bf in lower for bf in bad_fragments):
            return False
        # Reject very long or very short names
        words = name.split()
        if not (2 <= len(words) <= 10):
            return False
        # Reject names that are all lowercase (niche names are typically title case)
        if name == name.lower():
            return False
        # Reject strings that look like financial figures or calculations (Bug 5)
        if re.search(r'[£$×%]|\d+\s*/\s*month|\d+\s*customers|\d+\s*×', name):
            return False
        return True

    # Pattern A: "Niche 1: \"Name\"" or "Niche 1. \"Name\""
    for m in re.finditer(r'[Nn]iche\s+\d+[:.\s]+"([^"]{3,60})"', text):
        clean = m.group(1).strip()
        if _is_valid_name(clean, seen):
            seen.add(clean.lower())
            names.append(clean[:80])
            if len(names) >= 3:
                return names[:3]

    # Pattern B: "Candidate 1: \"Name\""
    for m in re.finditer(r'[Cc]andidate\s+\d+[:.\s]+"([^"]{3,60})"', text):
        clean = m.group(1).strip()
        if _is_valid_name(clean, seen):
            seen.add(clean.lower())
            names.append(clean[:80])
            if len(names) >= 3:
                return names[:3]

    # Pattern C: "**Name — VERDICT**" or "**Niche 1: Name**" (Skeptic format)
    for m in re.finditer(r'\*\*([A-Z][^*\n]{2,80})\*\*\s*(?:[–—-]\s*)?(?:SURVIVE|WEAK|KILL)', text, re.IGNORECASE):
        clean = m.group(1).strip()
        lower = clean.lower()
        if len(clean) > 3 and lower not in seen and 'niche' not in lower:
            seen.add(lower)
            names.append(clean[:80])
            if len(names) >= 3:
                return names[:3]
    # Also look for "Niche 1: Name**" format
    for m in re.finditer(r'[Nn]iche\s+\d+[:.\s]+\s*\*?\*?\s*([A-Z][^*\n]{2,80})\*?\*?', text):
        clean = m.group(1).strip().strip('*').strip()
        lower = clean.lower()
        if len(clean) > 3 and lower not in seen and 'niche' not in lower:
            seen.add(lower)
            names.append(clean[:80])
            if len(names) >= 3:
                return names[:3]

    # Pattern D: "Niche 1: Name" or "Candidate 1: Name" (unquoted, on its own line)
    for line in text.split('\n'):
        line_lower = line.lower()
        if any(phrase in line_lower for phrase in ['the user', 'let me', 'i need to', 'i must', 'my job', 'my instructions']):
            continue
        # Match "Niche 1: Name" where Name is a title-case word sequence
        m = re.search(r'^[Nn]iche\s+\d+[:.\s]+(?:[^\n]*?\s*[–—-]\s*)?([A-Z][a-zA-Z0-9\s]{2,40})\s*(?:\(|\[|–—-|$)', line)
        if m:
            clean = m.group(1).strip()
            if _is_valid_name(clean, seen):
                seen.add(clean.lower())
                names.append(clean[:80])
                if len(names) >= 3:
                    return names[:3]

    # Fallback: any double-quoted strings that look like product names
    quoted = re.findall(r'"([^"]{10,80})"', text)
    for q in quoted:
        clean = q.strip()
        if _is_valid_name(clean, seen):
            seen.add(clean.lower())
            names.append(clean[:80])
            if len(names) >= 3:
                break
    return names[:3]


def extract_objections(text: str) -> List[str]:
    """Extract bullet-point objections from Skeptic's output."""
    text = strip_meta_commentary(text)
    objections = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "• ")) and len(stripped) > 20:
            obj = stripped.lstrip("-*• ").strip()
            if any(kw in obj.lower() for kw in [
                "no evidence", "unverified", "assumption", "market",
                "competitor", "cac", "churn", "incumbent", "saturated", "risk"
            ]):
                objections.append(obj[:120])
    return objections[:5]


def strip_meta_commentary(text: str) -> str:
    """Strip model internal monologue (reasoning, self-instructions) before extraction.
    Kimi K2.6 outputs 500-2000 chars of meta-commentary before actual content.
    """
    # Heuristic: find the first line that looks like actual structured output
    # Skip lines that are clearly model self-talk
    meta_starts = [
        "the user wants me to", "the user is", "the user says", "the user message",
        "they want me to", "they are responding", "they previously",
        "key details from the prompt", "key details:", "key information:",
        "i have been given", "i have received", "i am given", "i was given",
        "i need to", "i must", "my job is", "my instructions", "my goal",
        "i was instructed", "i have been instructed", "according to my instructions",
        "i will", "let me think", "let me analyze", "let me consider", "actually,",
        "wait,", "looking at", "i should", "i can", "i have to", "i want to",
        "i would", "i could", "i might", "i may", "i am now", "i am the", "i am acting as",
        "now i am", "so now i am", "i need to check", "i need to look", "i need to re-read",
        "wait, i need to", "re-reading", "re-reading the", "hmm", "hmmm", "umm", "ugh",
        "oh", "ah", "okay", "ok", "well", "right", "yes", "no", "sure", "true", "false",
        "correct", "incorrect", "exactly", "precisely", "indeed", "absolutely",
        "definitely", "certainly", "obviously", "clearly", "naturally", "evidently",
        "apparently", "supposedly", "presumably", "arguably", "potentially", "likely",
        "probably", "possibly", "maybe", "perhaps", "hopefully", "ideally",
        "theoretically", "practically", "realistically", "honestly", "frankly",
        "personally", "subjectively", "objectively", "technically", "logically",
    ]
    lines = text.split("\n")
    result_lines = []
    for line in lines:
        stripped = line.strip().lower()
        # Skip if line starts with a meta-phrase (ignoring markdown bold/italic)
        clean_stripped = stripped.lstrip("*-_# ").lower()
        if any(clean_stripped.startswith(phrase) for phrase in meta_starts):
            continue
        # Skip if line is just a fragment (less than 10 chars after stripping)
        if len(stripped.lstrip("*-_# ")) < 10:
            continue
        result_lines.append(line)
    text_clean = "\n".join(result_lines)
    # Find actual content start: first structured header
    # Synthesizer uses: Niche 1:, Candidate 1:, Name:
    # Skeptic uses: **Name — VERDICT** or Name — VERDICT
    content_start = -1
    for pattern in [
        r'[Nn]iche\s+1[:.\s]',
        r'[Cc]andidate\s+1[:.\s]',
        r'(?:^|\n)\s*1\.\s+[Nn]ame[:.\s]',
        r'(?:^|\n)\s*\*\*[A-Z][^\n*]{3,50}\s*[–—-]\s*(?:SURVIVE|KILL|WEAK)',
        r'(?:^|\n)\s*[A-Z][^\n*]{3,50}\s*[–—-]\s*(?:SURVIVE|KILL|WEAK)',
        # Stage 4 pricing content: "1. **ProductName** — £XX/month" or "Proposed tiers"
        r'(?:^|\n)\s*1\.\s+\*\*[A-Z][^*\n]{2,50}\*\*\s*[–—-]\s*£\d',
        r'(?:^|\n)\s*[Pp]roposed\s+[Tt]iers?',
    ]:
        m = re.search(pattern, text_clean, re.IGNORECASE)
        if m:
            content_start = m.start()
            break
    if content_start > 100:
        text_clean = text_clean[content_start:]
    # Also apply regex removal for longer meta-commentary blocks
    text_clean = re.sub(
        r'(?im)^\s*(?:\*\*?)?(?:The user wants me to|I need to|I must|My job is|'
        r'My instructions are?|I will|Let me think|Let me analyze|Let me consider|'
        r'Actually,|Wait,|Looking at|I should|I can|I have to|I want to|I would|'
        r'I could|I might|I may|I am now|I am the|I am acting as|Now I am|'
        r'So now I am|I need to check|I need to look|I need to re-read|'
        r'Wait, I need to|Re-reading|Re-reading the|Hmm|Hmmm|Umm|Ugh|Oh|Ah|'
        r'Okay|OK|Well|Right|Yes|No|Sure|True|False|Correct|Incorrect|Exactly|'
        r'Precisely|Indeed|Absolutely|Definitely|Certainly|Obviously|Clearly|'
        r'Naturally|Evidently|Apparently|Supposedly|Presumably|Arguably|'
        r'Potentially|Likely|Probably|Possibly|Maybe|Perhaps|Hopefully|'
        r'Ideally|Theoretically|Practically|Realistically|Honestly|Frankly|'
        r'Personally|Subjectively|Objectively|Technically|Logically).*?(?:\n|$)',
        '',
        text_clean
    )
    # Remove "Looking at the conversation..." style blocks
    text_clean = re.sub(
        r'(?im)^\s*(?:\*\*?)?(?:Looking at the|Looking back|Looking carefully|'
        r'Wait, looking|Actually, looking|Re-reading|Re-reading the).*?(?:\n|$)',
        '',
        text_clean
    )
    return text_clean.strip()


def extract_synthesizer_ranking(transcript: List[Dict]) -> List[str]:
    """Extract Synthesizer's own ranking from Round 1 proposal order.
    First niche proposed = most promising from Synthesizer's perspective."""
    for entry in transcript:
        if entry.get("role") == "Synthesizer" and entry.get("round") == 1:
            names = extract_niche_names(strip_meta_commentary(entry["content"]))
            if names:
                return names[:3]
    return []


def extract_skeptic_ranking(transcript: List[Dict]) -> List[str]:
    """Extract Skeptic's ranking from Round 1 verdicts (SURVIVE > WEAK > KILL).
    Uses ONLY Round 1 — cleanest verdicts, least meta-commentary.
    Handles two Skeptic formats:
      A) **Name — VERDICT** (header inline verdict)
      B) **Niche 1: Name** + body + "Verdict: KILL/WEAK"
    Order: SURVIVE first, then WEAK, then KILL last."""
    verdict_scores = {"survive": 2, "weak": 1, "kill": -2}
    niche_scores: Dict[str, int] = {}
    for entry in transcript:
        if entry.get("role") != "Skeptic" or entry.get("round") != 1:
            continue
        text = strip_meta_commentary(entry.get("content", ""))

        # Format A: **Name — VERDICT**
        for m in re.finditer(
            r'(?:^|\n)\s*\*{0,2}\s*([A-Z][^\n*–—-]{3,80})\s*[–—-]\s*\[?\s*(SURVIVE|WEAK|KILL)\s*\]?',
            text,
        ):
            name = m.group(1).strip().strip('*').strip()
            verdict = m.group(2).upper()
            if len(name) > 5 and 'niche' not in name.lower():
                niche_scores[name] = max(
                    niche_scores.get(name, -999),
                    verdict_scores.get(verdict.lower(), 0),
                )

        # Format B: **Niche 1: Name** ... Verdict: KILL/WEAK/SURVIVE
        # Find all "Verdict:" lines and map them to the nearest preceding niche header
        for vm in re.finditer(r'[Vv]erdict[:\s]+(?:.*?(SURVIVE|WEAK|KILL))', text):
            verdict = vm.group(1).upper()
            pos = vm.start()
            # Look backward for the nearest **Niche X: Name** or **Name** header
            window = text[max(0, pos-800):pos]
            nm = None
            # Try "**Niche 1: Name**" or "**Name**" (with dash after)
            for pat in [
                r'\*\*([A-Z][^*\n]{2,80})\*\*',
                r'[Nn]iche\s+\d+[:.\s]+\s*\*?\*?\s*([A-Z][^*\n]{2,80})\*?\*?',
            ]:
                for n in re.finditer(pat, window):
                    nm = n
            if nm:
                name = nm.group(1).strip().strip('*').strip()
                if len(name) > 5 and 'niche' not in name.lower() and 'verdict' not in name.lower():
                    niche_scores[name] = max(
                        niche_scores.get(name, -999),
                        verdict_scores.get(verdict.lower(), 0),
                    )

    # Sort by score descending
    ranked = sorted(niche_scores.keys(), key=lambda n: niche_scores.get(n, 0), reverse=True)
    return ranked[:3]


def extract_kill_conditions(text: str) -> List[Dict]:
    """Extract genuine falsifiability kill conditions.
    Requires explicit 'Kill condition' header — no bare 'If' statements."""
    text = strip_meta_commentary(text)
    conditions = []
    # Only match lines that explicitly start with Kill condition marker
    pattern = re.compile(
        r'(?:^|\n)\s*(?:[-*•]\s*)?(?:\*\*)?[Kk]ill\s+[Cc]ondition(?:s)?(?:\s*\d+)?(?:\*\*)?[\s:]+'
        r'([Ii]f\s+[^.\n]{20,300}?'
        r'(?:is\s+(?:false|dead|not\s+true)|die[sd]?|fails?|cannot\s+proceed|'
        r'doesn\'t\s+exist|do(?:es)?\s+not\s+exist|exceeds|push|remains\s+unavailable|'
        r'requires|remains|falls\s+below|remains\s+above|cannot\s+legally|'
        r'niche\s+is\s+dead|this\s+niche\s+is\s+dead|this\s+niche\s+dies|'
        r'this\s+is\s+dead|abandon|not\s+viable))'
        r'[^.\n]*\.?',
        re.IGNORECASE | re.MULTILINE,
    )
    for m in pattern.finditer(text):
        cond = m.group(1).strip()
        if len(cond) > 25 and 'willingness_to_pay is false' not in cond.lower():
            conditions.append({
                "id": f"kc_{len(conditions)+1:02d}",
                "condition": cond[:250],
                "status": "proposed",
            })
            if len(conditions) >= 5:
                break
    return conditions


def format_kill_conditions(kill_conditions: List[Dict]) -> str:
    """Format kill conditions as a user message stimulus."""
    lines = ["Signed-off kill conditions:"]
    for kc in kill_conditions:
        lines.append(f"- {kc.get('id', '?')}: {kc.get('condition', '?')[:200]}")
    return "\n".join(lines)


def extract_pricing_tiers(text: str) -> List[Dict]:
    """Extract pricing tiers from Stage 4 Synthesizer output.
    Matches patterns like:
      - **Tier 1 — Free / £29 / £99**: description
      - Tier 1: Free (£0) - description
      - 1. Free Tier (£0/month): description
    Returns list of {name, price, period, description} dicts."""
    # Use raw text for structured extraction — strip_meta_commentary is too aggressive
    # for short lines like "CAC: £35" or "Starter — £9/mo"
    tiers = []
    seen = set()
    # Pattern: **Name — Price**: desc  or  **Name — Price** desc
    for m in re.finditer(
        r'(?:^|\n)\s*(?:[-*•]\s*)?(?:\*\*)?'
        r'([A-Z][^*\n—–-]{3,60}?)\s*[—–-]\s*'
        r'(£?\d+[\d,]*(?:\.\d+)?(?:\s*(?:\/\s*)?(?:month|mo|year|yr|one-time|ft|ftee)?)?)'
        r'(?:\*\*)?[:\s]*([^\n]{10,200}?)(?=\n|$|\s*\*\*)',
        text, re.IGNORECASE,
    ):
        name = m.group(1).strip()
        price_str = m.group(2).strip()
        desc = m.group(3).strip() if m.group(3) else ""
        key = (name.lower(), price_str.lower())
        if key not in seen and len(name) >= 3:
            seen.add(key)
            period = "month"
            if any(k in price_str.lower() for k in ["/yr", "year", "yr"]):
                period = "year"
            elif "one-time" in price_str.lower() or "ft" in price_str.lower():
                period = "one-time"
            # Strip currency symbol, slash, and period words for numeric value
            price_clean = re.sub(r'[£$,/]|\s*(?:month|mo|year|yr|one-time|ft|ftee)', '', price_str, flags=re.IGNORECASE).strip()
            try:
                price_val = float(price_clean) if price_clean else 0.0
            except ValueError:
                price_val = 0.0
            tiers.append({
                "name": name[:60],
                "price_str": price_str[:30],
                "price_value": price_val,
                "period": period,
                "description": desc[:200],
            })
            if len(tiers) >= 5:
                break
    # Fallback: simpler "Tier: Price" format
    if not tiers:
        for m in re.finditer(
            r'(?:^|\n)\s*(?:\d+\.\s+)?(?:\*\*)?'
            r'([A-Z][^*\n:]{3,50})\*?\*?\s*[:\(]\s*'
            r'(£?\d+[\d,]*(?:\.\d+)?)\s*(?:/\s*(mo|month|yr|year|one-time))?',
            text, re.IGNORECASE,
        ):
            name = m.group(1).strip()
            price_str = m.group(2).strip()
            period = m.group(3) if m.group(3) else "month"
            key = (name.lower(), price_str.lower())
            if key not in seen and len(name) >= 3:
                seen.add(key)
                price_clean = re.sub(r'[£$,]', '', price_str).strip()
                try:
                    price_val = float(price_clean) if price_clean else 0.0
                except ValueError:
                    price_val = 0.0
                tiers.append({
                    "name": name[:60],
                    "price_str": price_str[:30],
                    "price_value": price_val,
                    "period": period.lower(),
                    "description": "",
                })
                if len(tiers) >= 5:
                    break
    return tiers[:5]


def extract_unit_economics(text: str) -> Dict[str, Any]:
    """Extract unit economics metrics from Stage 4 output.
    Looks for CAC, LTV, gross margin, payback period.
    Returns dict with values and verification status."""
    # Use raw text for structured extraction — strip_meta_commentary filters short lines
    economics = {
        "cac": None,
        "ltv": None,
        "gross_margin": None,
        "payback_months": None,
        "verified": False,
        "cac_tier": None,  # "safe", "weak", "kill"
    }
    # CAC extraction
    cac_match = re.search(
        r'(?:CAC|customer acquisition cost)[\s:]*(?:£|\$)?(\d+[\d,]*(?:\.\d+)?)',
        text, re.IGNORECASE,
    )
    if cac_match:
        try:
            economics["cac"] = float(re.sub(r'[,$]', '', cac_match.group(1)))
        except ValueError:
            pass
    # LTV extraction — for "LTV = £55 / 0.035 = £1,571. CAC £35", take £1,571.
    # Key: only match values that follow an '=' sign (equation results), not incidental £ values.
    for ltv_line in re.finditer(r'(?:LTV|lifetime value)[^\n]+', text, re.IGNORECASE):
        assigned = re.findall(r'=\s*(?:£|\$)([\d,]+(?:\.\d+)?)', ltv_line.group(0))
        if assigned:
            try:
                economics["ltv"] = float(assigned[-1].replace(',', ''))
            except ValueError:
                pass
            break
        # Fallback: plain "LTV: £1,500" format with no equation
        # Use the FIRST £ value on this line (LTV is typically before other £ mentions like CAC)
        plain = re.findall(r'(?:£|\$)([\d,]+(?:\.\d+)?)', ltv_line.group(0))
        if plain:
            try:
                economics["ltv"] = float(plain[0].replace(',', ''))
            except ValueError:
                pass
            break
    # Gross margin
    margin_match = re.search(
        r'(?:gross margin|margin)[\s:]*(\d+(?:\.\d+)?)\s*%',
        text, re.IGNORECASE,
    )
    if margin_match:
        try:
            economics["gross_margin"] = float(margin_match.group(1))
        except ValueError:
            pass
    # Payback period
    payback_match = re.search(
        r'(?:payback|CAC payback|months to recover)[^\d:]*[:\s]*(\d+(?:\.\d+)?)\s*(?:months?|mo)',
        text, re.IGNORECASE,
    )
    if payback_match:
        try:
            economics["payback_months"] = float(payback_match.group(1))
        except ValueError:
            pass
    # CAC tier enforcement
    if economics["cac"] is not None:
        cac = economics["cac"]
        if cac <= 50:
            economics["cac_tier"] = "safe"
        elif cac <= 100:
            economics["cac_tier"] = "weak"
        else:
            economics["cac_tier"] = "kill"
        economics["verified"] = True
    return economics


def extract_sprint_plan(text: str) -> List[Dict]:
    """Extract validation sprint experiments from Stage 5 Synthesizer output.
    
    Uses a line-by-line parser to find experiment headers and collect their body text.
    
    Matches patterns like:
      **Experiment N: Name**
      Hypothesis: ...
      Metric: ...
      Success criteria: ...
      Duration: X days/weeks
      
    Or simpler:
      1. **Name** — Hypothesis. Metric: X. Success: Y. Duration: Z.
    """
    experiments = []
    seen = set()
    
    # Field prefixes that disqualify a line from being an experiment header
    field_prefixes = ("hypothesis", "metric", "kpi", "success", "criteria", "duration", "time", "timeline", "cost", "budget")
    
    def _is_header(line: str) -> Optional[str]:
        """Check if a line looks like an experiment header. Return name or None."""
        stripped = line.strip()
        # Skip empty or very short lines
        if len(stripped) < 10:
            return None
        # Skip field labels
        lower = stripped.lstrip("*-# ").lower()
        if any(lower.startswith(fp) for fp in field_prefixes):
            return None
        
        # Pattern 1: **Experiment N: Name**
        m = re.match(r'\*\*(?:[Ee]xperiment\s+)?(?:\d+[\.\):]\s+)?([A-Z][^*\n]{5,100}?)\*\*$', stripped)
        if m:
            return m.group(1).strip()
        
        # Pattern 2: Experiment N: Name (no bold)
        m = re.match(r'(?:[Ee]xperiment\s+)?(?:\d+[\.\):]\s+)?([A-Z][^\n]{5,100})$', stripped)
        if m:
            return m.group(1).strip()
        
        # Pattern 3: 1. **Name** — or 1. **Name**: 
        m = re.match(r'\d+[\.\):]\s+\*\*([^*\n]{5,100}?)\*\*\s*(?:[—–]|\:)', stripped)
        if m:
            return m.group(1).strip()
        
        # Reject plain prose sentences that don't look like experiment names
        # Heuristic: if it ends with a period and has no bold/experiment keyword, skip
        if stripped.endswith('.') and 'experiment' not in lower and '**' not in stripped:
            return None
        
        return None
    
    def _extract_fields(body: str) -> Dict[str, str]:
        """Extract hypothesis, metric, success, duration from body text."""
        hypothesis_match = re.search(r'(?:[Hh]ypothesis|[Hh]yp)[\s:]*([^\n]{10,300})', body)
        metric_match = re.search(r'(?:[Mm]etric|[Kk]PI)[\s:]*([^\n]{5,200})', body)
        success_match = re.search(r'(?:[Ss]uccess\s*[Cc]riteria|[Ss]uccess|[Cc]riteria)[\s:]*([^\n]{5,200})', body)
        duration_match = re.search(r'(?:[Dd]uration|[Tt]ime|[Tt]imeline)[\s:]*([^\n]{3,80})', body)
        return {
            "hypothesis": (hypothesis_match.group(1).strip() if hypothesis_match else "")[:200],
            "metric": (metric_match.group(1).strip() if metric_match else "")[:150],
            "success_criteria": (success_match.group(1).strip() if success_match else "")[:150],
            "duration": (duration_match.group(1).strip() if duration_match else "")[:50],
        }
    
    def _append_experiment(name: str, body: str) -> bool:
        """Extract fields and append experiment if it has any data. Returns True if appended."""
        key = name.lower()
        if key in seen or len(name) < 3:
            return False
        fields = _extract_fields(body)
        if not any(fields.values()):
            return False  # No fields found — don't add to seen or experiments
        seen.add(key)
        experiments.append({"name": name[:100], **fields})
        return True
    
    lines = text.split('\n')
    current_name = None
    current_body_lines = []
    
    for line in lines:
        name = _is_header(line)
        if name:
            # Save previous experiment if exists
            if current_name:
                _append_experiment(current_name, "\n".join(current_body_lines))
            
            current_name = name
            current_body_lines = []
        elif current_name is not None:
            current_body_lines.append(line)
    
    # Don't forget the last experiment
    if current_name:
        _append_experiment(current_name, "\n".join(current_body_lines))
    
    # Fallback: if no structured experiments found, try dash-separated single-line format
    if not experiments:
        for m in re.finditer(
            r'(?:^|\n)\s*(?:\d+[\.\):]\s+)?\*\*([^*\n]{5,100}?)\*\*\s*(?:[—–]|\:)\s*(.+)',
            text, re.IGNORECASE,
        ):
            name = m.group(1).strip()
            body = m.group(2).strip()
            lower_name = name.lower()
            if any(lower_name.startswith(fp) for fp in field_prefixes):
                continue
            if not name or len(name) < 10 or "hypothesis" not in body.lower():
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            
            experiments.append({
                "name": name[:100],
                "hypothesis": body[:200] if "hypothesis" in body.lower() else "",
                "metric": "",
                "success_criteria": "",
                "duration": "",
            })
            if len(experiments) >= 5:
                break
    
    return experiments[:5]


# ---------------------------------------------------------------------------
# Stage names
# ---------------------------------------------------------------------------
# Stage names
# ---------------------------------------------------------------------------
STAGE_NAMES = {
    1: "Niche Alignment",
    2: "Pain Point Research",
    3: "Solution Generation",
    4: "Business Model & Pricing",
    5: "Validation Sprint",
}


# ---------------------------------------------------------------------------
# Role prompts (set once in system message, never re-injected)
# ---------------------------------------------------------------------------
_SYNTHESIZER_SYSTEM = (
    "You are a startup analyst proposing niche ideas. Be constructive and evidence-based. "
    "Tag claims with [manifest], [inferred], or [unverified]. "
    "Output structured content only. No reasoning about instructions. No meta-commentary. "
    "Start your response with content immediately. No preamble, no meta-commentary, no repeating the prompt back."
)

_SKEPTIC_SYSTEM = (
    "You are a ruthless critic stress-testing startup niches. Demand evidence. "
    "State SURVIVE, KILL, or WEAK for each niche. No politeness. No reasoning about instructions. "
    "One full pivot allowed per session, then refine only. "
    "Focus your attacks on [unverified] claims first, then [inferred]. "
    "Accept [manifest] claims unless the manifest itself is flawed. "
    "Start your response with content immediately. No preamble, no meta-commentary, no repeating the prompt back."
)


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------

class KimiClient:
    """Low-level Kimi K2.6 client via the local Fireworks proxy.
    Tracks token usage per call for cost visibility."""

    def __init__(self):
        http_client = httpx.Client(
            headers={"Accept-Encoding": "identity"},
            timeout=120.0,
        )
        self.client = OpenAI(
            api_key=FIREWORKS_API_KEY,
            base_url=FIREWORKS_BASE_URL,
            http_client=http_client,
        )
        self.usage_log: List[Dict[str, int]] = []

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 2000, temperature: float = 0.6) -> str:
        """Make a single API call. No retries — caller decides what to do.
        Captures token usage into usage_log for cost tracking."""
        resp = self.client.chat.completions.create(
            model=KIMI_MODEL,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw = resp.choices[0].message.content or ""
        
        # Capture token usage if available
        usage = getattr(resp, "usage", None)
        if usage:
            self.usage_log.append({
                "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                "completion_tokens": getattr(usage, "completion_tokens", 0),
                "total_tokens": getattr(usage, "total_tokens", 0),
            })
        
        return raw

    def get_usage_summary(self) -> Dict[str, int]:
        """Return aggregated token usage across all calls."""
        if not self.usage_log:
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return {
            "prompt_tokens": sum(u["prompt_tokens"] for u in self.usage_log),
            "completion_tokens": sum(u["completion_tokens"] for u in self.usage_log),
            "total_tokens": sum(u["total_tokens"] for u in self.usage_log),
            "calls": len(self.usage_log),
        }

    def reset_usage(self) -> None:
        """Clear usage log (e.g., between stages)."""
        self.usage_log = []


# ---------------------------------------------------------------------------
# Agent classes with persistent conversation history
# ---------------------------------------------------------------------------

class Synthesizer:
    """Agent A: proposes, connects, refines. Maintains its own message history."""

    def __init__(self):
        self.client = KimiClient()
        self.history: List[Dict[str, str]] = []

    def initialize(self, stage_num: int, context: Dict[str, Any]):
        """Set up the conversation: system prompt + first user message with manifest.
        Called once per session."""
        manifest = context.get("manifest", {})
        segments = manifest.get("lead_segments", {})
        
        # Use refreshed live counts if available, else manifest estimates
        lead_counts = context.get("lead_counts", segments)
        def _fmt_count(v):
            try:
                return f"~{int(v):,}"
            except (ValueError, TypeError):
                return str(v)
        segment_summary = ", ".join([f"{k}: {_fmt_count(v)}" for k, v in lead_counts.items()])
        total_leads = sum(v for v in lead_counts.values() if isinstance(v, (int, float)))
        
        budget = manifest.get("budget_ceiling", {})
        timeline = manifest.get("timeline_months", "?")
        manifest_text = (
            f"Segments (with live lead counts): {segment_summary}\n"
            f"Total addressable leads: ~{total_leads:,}\n"
            f"Budget: £{budget.get('monthly_burn','?')}/mo, max CAC £{budget.get('max_cac','?')}\n"
            f"Timeline: {timeline} months"
        )

        rejections = context.get("rejected_niches", [])
        rejection_text = ""
        if rejections:
            lines = [f"- {r['niche'][:50]} (by {r['rejected_by']})" for r in rejections[-5:]]
            rejection_text = "Previously rejected niches:\n" + "\n".join(lines)

        evidence = context.get("required_evidence", [])
        evidence_text = ""
        if evidence:
            lines = [f"- {e['field']}: {e.get('status','pending')}" for e in evidence[:5]]
            evidence_text = "Evidence status:\n" + "\n".join(lines)

        segment_names = list(lead_counts.keys())
        user_content = (
            f"Manifest:\n{manifest_text}\n\n"
            f"{rejection_text}\n\n"
            f"{evidence_text}\n\n"
            f"Propose your 3 niche candidates now. RULES:\n"
            f"  1. Each niche MUST come from a DIFFERENT segment. "
            f"Available segments: {', '.join(segment_names)}. "
            f"Do not propose two niches from the same segment.\n"
            f"  2. Explore the full range — do not default to compliance or tax. "
            f"Think about operational pain, workflow automation, customer retention, "
            f"booking/scheduling, cash flow, inventory, compliance, and communication "
            f"problems across ALL segment types.\n"
            f"  3. For each niche: name, segment, customer pain (specific to that segment), "
            f"one kill condition ('If X is false, this niche is dead'), and revenue estimate "
            f"grounded in the segment lead count.\n"
            f"  4. The niche must be buildable within £{budget.get('monthly_burn','?')}/mo burn "
            f"and {timeline} months — but constraints are a filter at the end, not the starting point. "
            f"Generate bold ideas first.\n"
            f"Pick your 3 most compelling niches from 3 different segments."
        )

        self.history = [
            {"role": "system", "content": _SYNTHESIZER_SYSTEM},
            {"role": "user", "content": user_content},
        ]

    def respond(self, stimulus: str = "", max_tokens: int = 2000) -> str:
        """Append stimulus as user message, call API, append CLEAN response as assistant.
        Meta-commentary is stripped before storage so history stays clean."""
        if stimulus:
            self.history.append({"role": "user", "content": stimulus})
        raw = self.client.chat(self.history, max_tokens=max_tokens)
        clean = strip_meta_commentary(raw)
        # If stripping removes everything, keep a minimal version
        if not clean or len(clean) < 200:
            clean = raw.strip()
        self.history.append({"role": "assistant", "content": clean})
        return clean

    def respond_and_extract(self, stimulus: str = "", max_tokens: int = 2000) -> tuple:
        """respond() + regex extraction of niche names and pivot flag."""
        raw = self.respond(stimulus, max_tokens)
        niche_names = extract_niche_names(raw)
        pivot = "pivot" in raw.lower() and "restart" in raw.lower()
        claims = {
            "proposed_niche_ids": niche_names,
            "pivot_requested": pivot,
        }
        return raw, claims

    def rank(self) -> str:
        """Independent ranking — fresh 2-message call at 150 tokens.
        No debate-mode history, so preamble has no room to grow."""
        # Collect niche names already mentioned in this agent's history
        all_text = "\n".join(m["content"] for m in self.history if m["role"] == "assistant")
        known_niches = extract_niche_names(all_text)
        niches_list = " > ".join(known_niches[:5]) or "the 3 niches"
        messages = [
            {"role": "system", "content": (
                "You rank startup niches. Output exactly 3 niche names separated by ' > '. "
                "No extra text. No thinking. Just: Name1 > Name2 > Name3"
            )},
            {"role": "user", "content": (
                f"Rank these from best to worst opportunity: {niches_list}\n"
                f"Output ONLY: Name1 > Name2 > Name3"
            )},
        ]
        raw = self.client.chat(messages, max_tokens=150)
        # Pre-clean: drop lines that are clearly meta-commentary
        meta_phrases = [
            "the user wants me to", "i need to", "as the synthesizer", "as the skeptic",
            "looking at the", "let me rank", "here are the", "i will rank",
            "the niches are", "the user mentions", "output only", "the 3 niches",
        ]
        clean_lines = [
            l for l in raw.strip().split("\n")
            if not any(kw in l.lower() for kw in meta_phrases)
        ]
        clean_text = "\n".join(clean_lines)
        # Parse 'A > B > C' format from cleaned text
        parts = [p.strip().strip('"').strip('*') for p in clean_text.split(">") if len(p.strip().strip('"').strip('*')) > 2]
        if len(parts) >= 2:
            return json.dumps(parts[:3])
        # Fallback: line-by-line
        niche_lines = []
        for l in clean_lines:
            clean = re.sub(r"^\d+[\.\)]\s*", "", l).strip().strip('"').strip('*')
            if len(clean) > 4:
                niche_lines.append(clean)
        names = niche_lines[:3]
        if not names:
            # Second fallback: regex extraction from raw prose
            names = extract_niche_names(raw)[:3]
        return json.dumps(names) if names else raw

    def serialize(self) -> List[Dict]:
        """Return a copy of the conversation history for session persistence."""
        return self.history.copy()

    def restore(self, history: List[Dict]):
        """Restore conversation history from a previous session."""
        self.history = history.copy()

    def compress_history(self, max_tokens: int = 300) -> None:
        """Compress agent history between stages.
        
        Summarizes the full conversation into a single assistant message,
        keeping only the system prompt. This prevents context window bloat
        across stages.
        """
        if len(self.history) <= 2:
            return  # Nothing to compress (system + 1 message)
        
        # Extract all assistant responses (the agent's own outputs)
        assistant_messages = [m["content"] for m in self.history if m.get("role") == "assistant"]
        
        if not assistant_messages:
            return
        
        full_text = "\n\n".join(assistant_messages[:10])  # Last 10 responses
        
        # Generate summary using lightweight LLM call
        summary_prompt = (
            "Summarize the key decisions and conclusions from this deliberation "
            "in 200 words max. Focus on: approved niche/pain point/solution, "
            "key objections raised, and final consensus.\n\n"
            f"{full_text[:4000]}"
        )
        messages = [
            {"role": "system", "content": "You summarize deliberation transcripts. Be concise. No meta-commentary."},
            {"role": "user", "content": summary_prompt},
        ]
        
        try:
            resp = self.client.chat(messages, max_tokens=max_tokens, temperature=0.0)
            summary = strip_meta_commentary(resp).strip()
            
            if summary and len(summary) > 50:
                # Replace history with system + summary
                system_msg = next((m for m in self.history if m.get("role") == "system"), None)
                if system_msg:
                    self.history = [
                        system_msg,
                        {"role": "assistant", "content": f"[Stage Summary] {summary}"},
                    ]
        except Exception:
            # If compression fails, keep original history
            pass


class Skeptic:
    """Agent B: destroys weak arguments. Maintains its own message history."""

    def __init__(self):
        self.client = KimiClient()
        self.history: List[Dict[str, str]] = []
        self.pivot_used: bool = False  # Track whether a pivot has been used this session

    def initialize(self, stage_num: int, context: Dict[str, Any]):
        """Set up system prompt only. The first user stimulus comes from the orchestrator
        (Synthesizer's proposal + kill conditions)."""
        # Check if pivot was already used in a previous stage (from session context)
        self.pivot_used = context.get("pivot_used", False)
        
        system_prompt = _SKEPTIC_SYSTEM
        if self.pivot_used:
            system_prompt += " PIVOT ALREADY USED: You may NOT demand a full pivot again. Only refine objections."
        else:
            system_prompt += " One full pivot allowed per session, then refine only."
        
        self.history = [
            {"role": "system", "content": system_prompt},
        ]

    def respond(self, stimulus: str = "", max_tokens: int = 2000) -> str:
        """Append stimulus as user message, call API, append CLEAN response as assistant."""
        if stimulus:
            self.history.append({"role": "user", "content": stimulus})
        raw = self.client.chat(self.history, max_tokens=max_tokens)
        clean = strip_meta_commentary(raw)
        if not clean or len(clean) < 200:
            clean = raw.strip()
        self.history.append({"role": "assistant", "content": clean})
        return clean

    def respond_and_extract(self, stimulus: str = "", max_tokens: int = 2000) -> tuple:
        """respond() + regex extraction of objections and pivot flag."""
        raw = self.respond(stimulus, max_tokens)
        objections = extract_objections(raw)
        pivot_requested = bool(re.search(r'\bpivot\b.*\brestart\b|\brestart\b.*\bpivot\b', raw, re.IGNORECASE))
        
        # Mark pivot as used if requested (even if we can't actually pivot — this prevents double-pivoting)
        if pivot_requested:
            self.pivot_used = True
        
        claims = {
            "objections_raised": objections,
            "objections_resolved": [],
            "pivot_requested": pivot_requested,
        }
        return raw, claims

    def rank(self) -> str:
        """Independent ranking — fresh 2-message call at 150 tokens.
        Same logic as Synthesizer.rank()."""
        all_text = "\n".join(m["content"] for m in self.history if m["role"] == "assistant")
        known_niches = extract_niche_names(all_text)
        niches_list = " > ".join(known_niches[:5]) or "the 3 niches"
        messages = [
            {"role": "system", "content": (
                "You rank startup niches. Output exactly 3 niche names separated by ' > '. "
                "No extra text. No thinking. Just: Name1 > Name2 > Name3"
            )},
            {"role": "user", "content": (
                f"Rank these from best to worst opportunity: {niches_list}\n"
                f"Output ONLY: Name1 > Name2 > Name3"
            )},
        ]
        raw = self.client.chat(messages, max_tokens=150)
        meta_phrases = [
            "the user wants me to", "i need to", "as the synthesizer", "as the skeptic",
            "looking at the", "let me rank", "here are the", "i will rank",
            "the niches are", "the user mentions", "output only", "the 3 niches",
        ]
        clean_lines = [
            l for l in raw.strip().split("\n")
            if not any(kw in l.lower() for kw in meta_phrases)
        ]
        clean_text = "\n".join(clean_lines)
        parts = [p.strip().strip('"').strip('*') for p in clean_text.split(">") if len(p.strip().strip('"').strip('*')) > 2]
        if len(parts) >= 2:
            return json.dumps(parts[:3])
        niche_lines = []
        for l in clean_lines:
            clean = re.sub(r"^\d+[\.\)]\s*", "", l).strip().strip('"').strip('*')
            if len(clean) > 4:
                niche_lines.append(clean)
        names = niche_lines[:3]
        if not names:
            names = extract_niche_names(raw)[:3]
        return json.dumps(names) if names else raw

    def serialize(self) -> List[Dict]:
        return self.history.copy()

    def restore(self, history: List[Dict]):
        self.history = history.copy()

    def compress_history(self, max_tokens: int = 300) -> None:
        """Compress agent history between stages.
        
        Summarizes the full conversation into a single assistant message,
        keeping only the system prompt. This prevents context window bloat
        across stages.
        """
        if len(self.history) <= 2:
            return  # Nothing to compress (system + 1 message)
        
        # Extract all assistant responses (the agent's own outputs)
        assistant_messages = [m["content"] for m in self.history if m.get("role") == "assistant"]
        
        if not assistant_messages:
            return
        
        full_text = "\n\n".join(assistant_messages[:10])  # Last 10 responses
        
        # Generate summary using lightweight LLM call
        summary_prompt = (
            "Summarize the key decisions and conclusions from this deliberation "
            "in 200 words max. Focus on: approved niche/pain point/solution, "
            "key objections raised, and final consensus.\n\n"
            f"{full_text[:4000]}"
        )
        messages = [
            {"role": "system", "content": "You summarize deliberation transcripts. Be concise. No meta-commentary."},
            {"role": "user", "content": summary_prompt},
        ]
        
        try:
            resp = self.client.chat(messages, max_tokens=max_tokens, temperature=0.0)
            summary = strip_meta_commentary(resp).strip()
            
            if summary and len(summary) > 50:
                # Replace history with system + summary
                system_msg = next((m for m in self.history if m.get("role") == "system"), None)
                if system_msg:
                    self.history = [
                        system_msg,
                        {"role": "assistant", "content": f"[Stage Summary] {summary}"},
                    ]
        except Exception:
            # If compression fails, keep original history
            pass


# ---------------------------------------------------------------------------
# LLM-based extraction layer (primary) — replaces regex extraction
# Uses a lightweight 150-token LLM call to parse free-form output into JSON.
# Falls back to regex if the LLM call fails or returns invalid JSON.
# ---------------------------------------------------------------------------

_EXTRACTION_SCHEMAS = {
    "pricing_tiers": {
        "prompt": (
            "Extract all pricing tiers from the text below. "
            "Return ONLY a JSON array: [{{\"name\": \"...\", \"price_str\": \"...\", \"period\": \"month|year|one-time\", \"description\": \"...\"}}]"
            "If none found, return [].\n\nText:\n{text}"
        ),
        "fallback": extract_pricing_tiers,
    },
    "unit_economics": {
        "prompt": (
            "Extract unit economics from the text below. "
            "Return ONLY a JSON object: {{\"cac\": number|null, \"ltv\": number|null, "
            "\"gross_margin\": number|null, \"payback_months\": number|null}}. "
            "If a value is not found, use null.\n\nText:\n{text}"
        ),
        "fallback": extract_unit_economics,
    },
    "sprint_plan": {
        "prompt": (
            "Extract validation experiments from the text below. "
            "Return ONLY a JSON array: [{{\"name\": \"...\", \"hypothesis\": \"...\", "
            "\"metric\": \"...\", \"success_criteria\": \"...\", \"duration\": \"...\"}}]"
            "If none found, return [].\n\nText:\n{text}"
        ),
        "fallback": extract_sprint_plan,
    },
    "niche_names": {
        "prompt": (
            "Extract up to 3 niche names from the text below. "
            "Return ONLY a JSON array of strings: [\"Name 1\", \"Name 2\"]"
            "If none found, return [].\n\nText:\n{text}"
        ),
        "fallback": extract_niche_names,
    },
    "kill_conditions": {
        "prompt": (
            "Extract kill conditions (statements of form 'If X is false, this niche is dead') "
            "from the text below. Return ONLY a JSON array of strings.\n\nText:\n{text}"
        ),
        "fallback": extract_kill_conditions,
    },
}


def _llm_extract(field: str, text: str) -> Any:
    """Primary extractor: lightweight LLM call to parse free-form output.
    Falls back to regex-based extraction if the LLM fails."""
    schema = _EXTRACTION_SCHEMAS.get(field)
    if not schema:
        raise ValueError(f"Unknown extraction field: {field}")

    prompt = schema["prompt"].format(text=text[:3000])  # Truncate to avoid excessive tokens
    messages = [
        {"role": "system", "content": "You extract structured data from text. Output valid JSON only. No commentary."},
        {"role": "user", "content": prompt},
    ]

    try:
        client = KimiClient()
        raw = client.chat(messages, max_tokens=150, temperature=0.0)
        raw = raw.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(raw)
    except Exception:
        # Fallback to regex
        return schema["fallback"](text)


def llm_extract_pricing_tiers(text: str) -> List[Dict]:
    result = _llm_extract("pricing_tiers", text)
    if isinstance(result, list):
        return result
    return extract_pricing_tiers(text)


def llm_extract_unit_economics(text: str) -> Dict[str, Any]:
    result = _llm_extract("unit_economics", text)
    if isinstance(result, dict):
        # Ensure numeric values
        for key in ["cac", "ltv", "gross_margin", "payback_months"]:
            if result.get(key) is not None:
                try:
                    result[key] = float(result[key])
                except (ValueError, TypeError):
                    result[key] = None
        return result
    return extract_unit_economics(text)


def llm_extract_sprint_plan(text: str) -> List[Dict]:
    result = _llm_extract("sprint_plan", text)
    if isinstance(result, list):
        return result
    return extract_sprint_plan(text)


def llm_extract_niche_names(text: str) -> List[str]:
    result = _llm_extract("niche_names", text)
    if isinstance(result, list):
        return [str(r) for r in result if isinstance(r, (str, int, float))]
    return extract_niche_names(text)


def llm_extract_kill_conditions(text: str) -> List[Dict]:
    result = _llm_extract("kill_conditions", text)
    if isinstance(result, list) and len(result) > 0:
        # LLM returns list of strings; fallback returns list of dicts
        if isinstance(result[0], dict):
            return result  # Already formatted by fallback
        return [
            {"id": f"kc_{i+1:02d}", "condition": str(cond), "status": "proposed"}
            for i, cond in enumerate(result)
            if isinstance(cond, str) and len(cond) > 15
        ]
    return extract_kill_conditions(text)
