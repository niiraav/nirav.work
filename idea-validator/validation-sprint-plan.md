# Validation Sprint: AI Agent Sessions vs. CreatorGrowth

---

## TLDR Recommendation

Run both in parallel. Candidate 1 has higher revenue ceiling and stronger existing signal — prioritize it. Candidate 2 is your fallback if C1 stalls by Day 6.

---

## 1. Validation Methods

### Candidate 1: AI Agent Session Sharing

**Where to find targets:**
- HN threads: Search "Claude Code", "Cursor", "Windsurf" — reply directly to comments expressing the pain
- Discord: Claude Code official server (`#show-claude-code`, `#feedback`), Cursor Discord, Windsurf Discord
- Reddit: r/ClaudeAI, r/cursor_ai, r/ChatGPTCoding — DM users with high-effort posts about workflow
- LinkedIn: Search "engineering manager" + "AI coding" — filter by companies with 10-50 engineers

**Format:** Async DM first. If they reply, 20-min Loom or voice note exchange (no calendars).

**Goal:** 15 conversations in 10 days.

---

### Candidate 2: CreatorGrowth

**Where to find targets:**
- Reddit: r/gumroad, r/sellingdigitalproducts, r/passiveincome — DM creators complaining about marketing/traffic
- Twitter/X: Search "gumroad" filter:replies — people venting about low sales
- Gumroad itself: Buy a cheap product ($5-10), reply to the receipt email asking the creator a question — instant warm contact

**Format:** Twitter DM or Reddit DM. Short. No pitch.

**Goal:** 15 conversations in 10 days.

---

## 2. Scripts

### Candidate 1 — Cold DM (HN/Discord/Reddit)

```
Hey [name] — saw your comment about [specific thing they said about agent sessions/workflow].

I'm trying to understand how teams actually manage this. Quick question: when you or a teammate needs to pick up where someone else left off in an agent session, what do you do right now?

No pitch, just mapping the problem.
```

**3 follow-up questions that reveal WTP:**

1. "Has a lost session ever actually cost you time or caused a bug? What happened?" *(past behavior = real pain)*
2. "What did you try to fix it — Slack threads, notes, anything?" *(proxy spend = willingness to effort-solve)*
3. "If a tool gave you full searchable history + replay of every agent session across your team, what would that be worth per month — ballpark?" *(direct but positioned as estimation, not sales)*

---

### Candidate 2 — Cold DM (Reddit/Twitter)

```
Hey — saw your post about [specific frustration with Gumroad marketing/sales].

I'm researching how creators handle the "traffic problem" after launch. What's your current setup for getting people to your Gumroad page — do you have a separate landing page, or do you send people directly to Gumroad?
```

**3 follow-up questions that reveal WTP:**

1. "Have you ever paid for something to help with this — copywriter, ads, a theme, anything?" *(past spend = validated pain)*
2. "If you could wake up tomorrow and your Gumroad product had a proper landing page with good copy — what would change for you?" *(desired outcome, not feature)*
3. "There are tools that auto-build landing pages from your Gumroad data. Have you seen any? What stopped you from trying them?" *(discover blockers before they kill your idea)*

---

## 3. Decision Framework

### Strong "Build It" signal (need 3+ of these across 8+ conversations):
- Unprompted asks "when can I try this?" or "is there a waitlist?"
- Mentions a specific dollar amount they'd pay without being pushed
- Describes having paid for a workaround (Notion, Loom, hiring, etc.)
- Expresses frustration at current state in detail (specificity = pain)
- Offers to intro you to their team/colleagues

### "Kill It" signal (if 2+ of these appear consistently):
- "That's a nice idea but I haven't really needed it"
- Describes a free workaround they're happy with
- Vague positive ("sounds cool") with no follow-up questions from them
- Can't articulate what they'd lose without it

### "Need More Data" (if you're stuck):
- Fewer than 8 conversations completed
- Mixed signals: some interest, no commitment
- → Extend 3 more days, change your opener, try a different channel

### Minimum threshold to commit:
- **C1:** 3 out of 12 conversations show at least 2 "build it" signals, including ≥1 mention of a dollar range
- **C2:** 4 out of 12 conversations, including ≥2 people who've paid for something similar

---

## 4. Day-by-Day Timeline

| Day | Time | Task |
|-----|------|------|
| 1 | 1h | Build target lists. C1: 20 HN/Discord users. C2: 20 Reddit/Twitter creators. Save in a simple table (name, platform, link, note). |
| 2 | 1h | Send first 10 DMs for C1. Keep message exact — don't customize beyond `[specific thing]`. |
| 3 | 1h | Send first 10 DMs for C2. Log C1 replies, follow up with Q1. |
| 4 | 1h | Follow up C1 replies with Q2-3. Send 5 more C1 DMs to new targets. |
| 5 | 1h | Follow up C2 replies with Q2-3. Send 5 more C2 DMs. Mid-sprint gut check: which feels more alive? |
| 6 | 1h | **Triage day.** Count signals. If C1 is clearly winning → drop C2, go deeper on C1 (ask for intros to teammates). If C2 is winning → same. If tied → continue both. |
| 7 | 1h | Deepest conversations: focus on the 3-4 most engaged people. Ask them: "What would make this a no-brainer to pay for?" |
| 8 | 1h | Mop-up: reply to any laggard responses, send 3 final DMs to highest-signal channels. |
| 9 | 30m | No new outreach. Reread every conversation. Score each 1-3 on WTP signal. |
| 10 | 1h | Decision. Write 3 sentences: what you heard, what it means, what you're building. Done. |

---

## 5. Risk Mitigation

**If C1 fails (no WTP signal by Day 6):**
The idea may be real but the buyer isn't a single engineer — it's an engineering manager or CTO. Pivot your DM targets to EMs at Series A/B startups. That's a different sale, not a dead idea.

**If C2 fails (no WTP signal by Day 6):**
The pain is real but $19/month may be too cheap to cut through noise, or creators don't trust landing pages they didn't write. Test a $49 "done-for-you landing page audit" offer instead — higher price signals more value.

**If both fail:**
Don't pivot to a third idea. You have one more lever: the *channel* was wrong, not the idea. Both ideas have real communities — you likely hit the wrong sub-forums or wrote an opener that telegraphed "I'm selling." Try one more week with a different opener on the stronger-signal idea before abandoning.

**Absolute fallback (Day 10, nothing worked):**
Go back to the 32 HN posts on C1. Find the 5 most specific complaints. Post a comment — not a DM — something like: *"I'm building something for exactly this. What would session sharing actually need to do to be useful for your team?"* Public thread = lower friction, more replies, new signal.

---

## Tracking Template

| # | Name | Platform | Idea | Date DM'd | Replied? | Q1 | Q2 | Q3 | Signal (1-3) | Notes |
|---|------|----------|------|-----------|----------|----|----|----|----|-------|

**Signal scoring:** 1 = polite but no pain, 2 = real pain no WTP, 3 = real pain + WTP signal

Commit to build when you have **5+ scores of 3** on one idea.
