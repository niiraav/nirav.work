# AI Idea Validation Framework

## What This Is

A local Python CLI tool that runs Claude (Director) and Kimi K2.6 (Researcher) through a structured 5-stage discussion pipeline to validate startup ideas. The output is Obsidian-formatted markdown saved directly to your vault.

The tool automates the manual workflow of switching between Claude and OpenCode — both models research, question, critique, and converge on a definitive plan without you in the loop at every step.

---

## Model Roles

| Model | Role | What it does |
|---|---|---|
| **Kimi K2.6** | Researcher + Questioner | Heavy lifting: scrapes platforms, mines pain points, sizes markets, queries Supabase leads. Asks Claude probing questions and suggests 2-3 approaches to choose between. |
| **Claude** | Director + Decider | Reviews Kimi's synthesis, answers questions, picks approaches, identifies gaps, and makes final stage advancement calls. |

Both models critique each other's conclusions. The loop is a discussion converging into an absolute, actionable plan.

---

## The Pipeline

```
User Input: niche candidate(s) OR "start fresh"
        ↓
  Orchestrator (Python CLI)
  ┌────────────────────────────────────────────────────────────────┐
  │  STAGE 1: Niche Identification                                  │
  │  → Kimi researches lead base segments, suggests 3 niches +     │
  │    asks Claude: "which angle matters most?"                    │
  │  → Claude directs: narrows to 1-3, explains reasoning          │
  │                                                                 │
  │  STAGE 2: Multi-Platform Pain Point Research                    │
  │  → Kimi runs searches across Reddit, Quora, G2, Trustpilot,   │
  │    LinkedIn, niche forums                                      │
  │  → Kimi asks: "should I dig deeper on pain point #2?"          │
  │  → Claude answers and directs the next angle                   │
  │                                                                 │
  │  STAGE 3: Pain Point Analysis & Ranking                        │
  │  → Kimi synthesises and ranks by frequency × intensity         │
  │  → Kimi asks: "ranking assumes X — do you agree?"              │
  │  → Claude validates or adjusts with reasoning                  │
  │                                                                 │
  │  STAGE 4: Solution Generation + Business Model                  │
  │  → Kimi generates 3 solutions (5 frameworks applied)           │
  │  → Kimi asks: "Solution B has the best moat but lowest leads   │
  │    — does that matter given your constraints?"                 │
  │  → Claude decides, both stress-test the moat                   │
  │                                                                 │
  │  STAGE 5: Validation Sprint Plan                               │
  │  → Kimi drafts cold email sequence + success criteria          │
  │  → Claude reviews hook, makes Go/No-Go call                    │
  └────────────────────────────────────────────────────────────────┘
        ↓
  Obsidian Markdown → saved to startup-idea-lab/
```

---

## Platform Research Coverage (Stage 2)

| Platform | What it extracts |
|---|---|
| Reddit | Authentic frustrations, workarounds, emotional language |
| Quora | "Why doesn't X exist?" questions, professional pain points |
| G2 / Capterra | Competitor reviews — what existing tools are missing |
| Trustpilot | Incumbent complaints from real customers |
| LinkedIn | Industry professional complaints, job post signals |
| Niche forums | Trade-specific communities (UKBusinessForums, etc.) |

Search uses `duckduckgo-search` (free, no API key required). Brave Search API is the fallback if DuckDuckGo rate-limits.

---

## Convergence Rules

Per stage (max 3 rounds):
- **Confidence ≥ 70%** → advance to next stage
- **Confidence < 40%** → escalate, write `NEEDS-HUMAN-*.md` to Obsidian
- **Max rounds hit without convergence** → escalate

Human review files include the exact unresolved disputes and a resume command to continue where you left off.

---

## Setup

```bash
cd idea-validator
pip install -r requirements.txt
cp .env.example .env
# Fill in ANTHROPIC_API_KEY, MOONSHOT_API_KEY, and OBSIDIAN_PATH
source .env
```

Check your Moonshot API dashboard or OpenCode config for the exact Kimi K2.6 model ID and set it as `KIMI_MODEL` in `.env`.

---

## Usage

```bash
# Start fresh
python main.py --mode fresh

# Validate a specific niche from Stage 1
python main.py --niche "MOT Reminder SaaS" --lead-focus automotive

# Start from Stage 2 (skip niche identification)
python main.py --niche "MOT Reminder SaaS" --start-stage 2

# Resume a saved session at Stage 3
python main.py --resume session_20260517_143022 --stage 3

# List all sessions
python main.py --list

# Run only Stages 2-4
python main.py --niche "Beauty Salon Booking" --start-stage 2 --end-stage 4
```

---

## File Structure

```
idea-validator/
├── main.py              — CLI entrypoint
├── orchestrator.py      — stage loop, convergence logic, escalation
├── agents.py            — Claude + Kimi clients, system prompts per stage
├── tools.py             — DuckDuckGo search, Supabase lead queries
├── output.py            — Obsidian markdown renderer
├── config.py            — API keys, paths, thresholds (from env vars)
├── requirements.txt
├── .env.example
├── sessions/            — JSON session state (auto-created)
└── templates/
    ├── validated-idea.md
    └── escalation.md
```

---

## Pre-Validated Niches (from lead-base-startup-niche-analysis.md)

These can enter the pipeline at Stage 2 or later:
1. **MOT Reminder + Garage Retention Tool** — 8,200 automotive leads, DVLA API moat
2. **No-Commission Booking for Beauty Salons** — 5,300 leads, anti-Fresha positioning
3. **Email Marketing for Vape/Restricted Ecom** — 1,100+ leads, banned from ad platforms

```bash
python main.py --niche "MOT Reminder SaaS" --start-stage 2 --lead-focus automotive
```

---

## Gstack Skills Integration

The gstack skills (`/browse`, `/investigate`, `/office-hours`) run inside Claude Code or OpenCode sessions — they are not called programmatically by this tool. Use them manually when:
- You want deeper page scraping during Stage 2 research
- You want a YC-style `/office-hours` diagnostic on a Stage 1 niche candidate
- You want a CEO-level `/plan-ceo-review` on a Stage 4 solution concept

Then paste the output into your next `python main.py` run by adding it to the session transcript JSON.
