import json
import anthropic
from openai import OpenAI
from config import (
    ANTHROPIC_API_KEY,
    MOONSHOT_API_KEY,
    CLAUDE_MODEL,
    KIMI_MODEL,
    MOONSHOT_BASE_URL,
)

STAGE_NAMES = {
    1: "Niche Identification",
    2: "Multi-Platform Pain Point Research",
    3: "Pain Point Analysis & Ranking",
    4: "Solution Generation & Business Model",
    5: "Validation Sprint Plan",
}

_KIMI_PROMPTS = {
    1: """You are a startup market researcher specialising in UK SMBs.
The user has 138,258 verified UK SMB business emails in Supabase — the segments are listed below.
Your job each turn:
1. Research 3 niche candidates. For each: addressable market, key competitors, moat potential, and how many leads from the base it targets.
2. Synthesise clearly — name real competitors, reference real data where you know it.
3. End with: (a) 1-2 specific questions for Claude to help prioritise, (b) 2-3 ranked approaches.
Always bias toward niches where the lead base gives a direct, immediate GTM edge.""",

    2: """You are conducting pain point research across multiple platforms for a specific niche.
Given search results provided, for each platform:
1. Extract significant pain points with direct quotes as evidence.
2. Assess frequency (how often it appears) and intensity (emotional charge 1-5).
3. Note any workarounds customers have created — these signal strong unmet needs.
4. Flag pain points shared across multiple platforms — cross-platform signal is strongest.
End with: (a) which 2-3 pain points deserve deeper research and why, (b) 2 suggested next search angles.
Never generalise — every claim needs a quote or source link.""",

    3: """You are a market research analyst synthesising pain point data.
Given the pain points collected across all research rounds:
1. Rank them by: frequency × intensity × solvability score.
2. Identify deal-breakers vs nice-to-haves.
3. Note which existing solutions fail hardest against each — these are the openings.
4. Flag any pain points that look like venting rather than structural problems.
End with: (a) your ranking and the assumptions it rests on, (b) ask Claude whether those assumptions hold given their constraints.""",

    4: """You are a business opportunity strategist. Apply all 5 lenses to generate 3 solution concepts:
1. Market Segmentation — underserved sub-niche
2. Product Differentiation — premium, simplified, or specialised version
3. Business Model Innovation — subscription, freemium, marketplace, usage-based
4. Distribution & Marketing — cold email from lead base is always available
5. New Paradigm — emerging tech, regulation change, or proprietary data moat

For each solution concept output:
- Name, 2-3 sentence description
- Key differentiator and moat (what stops a funded competitor cloning this in 6 months?)
- Business model with rough pricing
- How it addresses the top confirmed pain points
- Cold email hook: 1-2 sentences you could send to leads TODAY
- Estimated lead count from available base

End with: (a) which solution has the strongest moat and why, (b) ask Claude about trade-offs given their stated constraints.""",

    5: """You are writing a concrete validation sprint plan.
Produce:
1. Target segment from lead base with estimated count
2. Cold email sequence — 3 emails: hook → value prop → CTA
3. Success criteria: what does "go" look like? (e.g. "3 positive replies from 50 sends within 7 days")
4. Community/forum threads to monitor for organic signal
5. Minimum evidence required before writing a single line of code

End with: ask Claude to review the cold email hook — is it specific enough? Does it reference the sharpest confirmed pain point?""",
}

_CLAUDE_PROMPTS = {
    1: """You are a startup strategy director reviewing niche research.
Your job:
1. Critically evaluate each niche candidate — which has the strongest signal and why?
2. Identify what's missing — what single data point would change your view?
3. Make a clear direction decision: which 1-3 niches advance, with explicit reasoning.
4. Challenge vague claims or unsupported assumptions directly.
You have 138,258 UK SMB emails as a GTM weapon. Weight opportunities that can be cold-emailed immediately.""",

    2: """You are reviewing the quality of pain point research.
Your job:
1. Evaluate whether pain points are real and acute vs mild inconveniences.
2. Identify gaps — platforms not yet searched, voices not yet heard.
3. Direct Kimi: what specific angle to search next, OR confirm research is sufficient to advance.
4. Challenge any pain point that seems like noise. "It's complicated" is not a pain point.
Push for specificity. Vague pain points produce vague solutions.""",

    3: """You are validating a pain point ranking.
Your job:
1. Challenge the ranking — does the order reflect genuine switching urgency?
2. Ask: which pain point, if solved overnight, would cause customers to switch immediately?
3. Identify any pain points specific to the UK SMB lead base characteristics (tech-conservative, cash-flow sensitive, CIS/VAT exposure).
4. Make a call: is this ranking solid enough to build solutions against, or does one key gap need closing?""",

    4: """You are the final decision-maker on solution selection.
Your job:
1. Review the 3 solution concepts — which has the most durable moat?
2. For your preferred candidate: what is the single biggest risk, and what evidence would mitigate it?
3. Select one solution with clear reasoning.
4. Stress-test the cold email hook — would YOU click this if you were a garage owner / salon owner / etc.?
5. Direct Kimi to revise if the hook is weak.""",

    5: """You are reviewing a validation sprint plan before leads are emailed.
Your job:
1. Is the success criteria specific and honest? (Not too easy, not impossible.)
2. Is the cold email hook referencing the sharpest confirmed pain point?
3. Is the minimum signal bar set at a level that would actually de-risk the build?
4. Make the Go/No-Go call with a confidence score (0-100) and explicit reasoning.
This is the final gate before anyone writes a line of code. Be decisive.""",
}

_CONVERGENCE_SYSTEM = """Evaluate whether a stage discussion has reached sufficient conclusion to advance.
Output ONLY valid JSON — no preamble, no markdown, no explanation outside the JSON:
{
  "confidence": <integer 0-100>,
  "action": "<advance|continue|escalate>",
  "confirmed_points": ["point 1", "point 2"],
  "disputed_points": ["contested point 1"],
  "reasoning": "one sentence"
}
Rules:
- confidence >= 70 → "advance"
- confidence < 40 → "escalate"
- otherwise → "continue"
- escalate if: deadlock after multiple rounds, a load-bearing point is unresolved, or fundamental viability is in question."""


class ClaudeAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def turn(self, stage_num: int, transcript: str) -> str:
        prompt = (
            f"## Stage {stage_num}: {STAGE_NAMES[stage_num]}\n\n"
            f"## Discussion so far:\n{transcript}\n\n"
            "Your turn as Director. Review Kimi's latest output and provide your direction, "
            "answers to their questions, and any critiques or gaps you've identified."
        )
        msg = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            system=_CLAUDE_PROMPTS[stage_num],
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text

    def decide_convergence(self, stage_num: int, transcript: str) -> dict:
        prompt = f"Stage {stage_num} ({STAGE_NAMES[stage_num]}) transcript:\n\n{transcript}\n\nOutput convergence JSON:"
        msg = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=400,
            system=_CONVERGENCE_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
        if "```" in text:
            parts = text.split("```")
            text = parts[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)


class KimiAgent:
    def __init__(self):
        self.client = OpenAI(api_key=MOONSHOT_API_KEY, base_url=MOONSHOT_BASE_URL)

    def turn(self, stage_num: int, search_results: str, transcript: str) -> str:
        parts = [f"## Stage {stage_num}: {STAGE_NAMES[stage_num]}"]
        if search_results:
            parts.append(f"## Search Results:\n{search_results}")
        if transcript:
            parts.append(f"## Discussion so far:\n{transcript}")
        parts.append(
            "Your turn as Researcher. Synthesise your findings, ask your questions, "
            "and suggest 2-3 approaches for Claude to choose between."
        )
        user_content = "\n\n".join(parts)

        response = self.client.chat.completions.create(
            model=KIMI_MODEL,
            messages=[
                {"role": "system", "content": _KIMI_PROMPTS[stage_num]},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2000,
        )
        return response.choices[0].message.content
