import os
from datetime import date
from config import OBSIDIAN_PATH


def _safe_filename(text: str) -> str:
    return "".join(c if c.isalnum() or c in " -_" else "-" for c in text).strip()


def write_final(session: dict) -> str:
    """Render and save the final validated-idea markdown to the Obsidian vault."""
    niche = session["niche"]
    today = date.today().isoformat()
    confidence = session.get("final_confidence", 0)
    verdict = "Go" if confidence >= 70 else "No-Go"

    confirmed = []
    disputed = []
    for stage_key, stage_data in session.get("stages", {}).items():
        confirmed.extend(stage_data.get("confirmed_points", []))
        disputed.extend(stage_data.get("disputed_points", []))

    confirmed_rows = "\n".join(f"| {p} | — | — |" for p in confirmed) or "| — | — | — |"
    disputed_section = "\n".join(f"- {p}" for p in disputed) or "_None_"

    transcript_excerpt = _build_transcript_excerpt(session.get("transcript", []))

    content = f"""---
title: "{niche} — Validation Report"
date: {today}
niche: "{niche}"
confidence: {confidence}
verdict: "{verdict}"
tags:
  - startup
  - validated
  - {_safe_filename(niche).lower().replace(' ', '-')}
---

# {niche} — Validation Report

## Verdict: {verdict}
**Confidence**: {confidence}%
**Validated**: {today}

---

## Confirmed Pain Points

| Pain Point | Evidence | Intensity |
|---|---|---|
{confirmed_rows}

## Disputed Points

{disputed_section}

---

## Discussion Summary

{transcript_excerpt}

---

## Next Steps

_See validation sprint plan in Stage 5 of the session transcript._
"""

    filename = f"{today}-{_safe_filename(niche)}.md"
    path = os.path.join(OBSIDIAN_PATH, filename)

    os.makedirs(OBSIDIAN_PATH, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

    print(f"\nSaved to Obsidian: {path}")
    return path


def write_escalation(session: dict, stage_num: int, reason: str, disputed_points: list[str] = None) -> str:
    """Write a NEEDS-HUMAN review file to Obsidian."""
    niche = session["niche"]
    today = date.today().isoformat()
    disputed_points = disputed_points or []

    disputed_section = "\n".join(f"- {p}" for p in disputed_points) or "_No specific disputed points logged._"

    content = f"""---
title: "NEEDS HUMAN REVIEW — {niche} Stage {stage_num}"
date: {today}
niche: "{niche}"
stage: {stage_num}
reason: "{reason}"
tags:
  - startup
  - escalated
---

# NEEDS HUMAN REVIEW — {niche}
**Stage {stage_num} escalated on {today}**
**Reason**: {reason}

---

## Disputed / Unresolved Points

{disputed_section}

## What Would Resolve This

Review the transcript in the session JSON and address the disputed points above.
Once resolved, resume with:
```
python main.py --resume {session['session_id']} --stage {stage_num}
```

## Session File

`idea-validator/sessions/{session['session_id']}.json`
"""

    filename = f"NEEDS-HUMAN-{_safe_filename(niche)}-stage{stage_num}-{today}.md"
    path = os.path.join(OBSIDIAN_PATH, filename)

    os.makedirs(OBSIDIAN_PATH, exist_ok=True)
    with open(path, "w") as f:
        f.write(content)

    print(f"\nEscalation saved to Obsidian: {path}")
    return path


def _build_transcript_excerpt(transcript: list[dict]) -> str:
    if not transcript:
        return "_No transcript available._"
    lines = []
    for entry in transcript[-6:]:  # last 6 turns for the summary
        role = entry.get("role", "Unknown")
        stage = entry.get("stage", "?")
        content = entry.get("content", "")[:400]
        lines.append(f"**[Stage {stage} — {role}]**\n{content}\n")
    return "\n".join(lines)
