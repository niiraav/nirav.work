import time
from ddgs import DDGS
from config import SEARCH_PLATFORMS, LEAD_BASE_SEGMENTS, SUPABASE_URL, SUPABASE_KEY

_PAIN_TERMS = (
    '"my biggest struggle" OR "I wish" OR "why doesn\'t" OR "frustrated" OR '
    '"terrible" OR "waste of time" OR "workaround" OR "I learned" OR '
    '"problem with" OR "drives me crazy" OR "can\'t believe" OR "regret"'
)

_PLATFORM_QUERY_TEMPLATES = {
    "reddit.com": 'site:reddit.com "{niche}" ({pain_terms}) inurl:comments',
    "quora.com": 'site:quora.com "{niche}" ("why doesn\'t" OR "struggling" OR "advice" OR "how do I")',
    "g2.com": 'site:g2.com "{competitor_or_niche}" ("cons" OR "missing" OR "wish it had" OR "doesn\'t")',
    "trustpilot.com": 'site:trustpilot.com "{competitor_or_niche}" ("terrible" OR "awful" OR "disappointing" OR "switch")',
    "linkedin.com": 'site:linkedin.com "{niche}" ("challenge" OR "pain point" OR "frustrated" OR "problem")',
}


def build_query(niche: str, platform_domain: str, competitor: str = "") -> str:
    template = _PLATFORM_QUERY_TEMPLATES.get(platform_domain)
    if not template:
        return f'"{niche}" {_PAIN_TERMS}'
    competitor_or_niche = competitor if competitor else niche
    return template.format(
        niche=niche,
        pain_terms=_PAIN_TERMS,
        competitor_or_niche=competitor_or_niche,
    )


def search_platform(query: str, max_results: int = 8) -> list[dict]:
    """Run a DuckDuckGo text search and return results as dicts with title/url/body."""
    try:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
    except Exception as e:
        return [{"title": "Search error", "href": "", "body": str(e)}]


def run_stage_searches(niche: str, competitor: str = "") -> str:
    """Search across all configured platforms for a niche and return formatted results."""
    all_results = []

    for domain, label in SEARCH_PLATFORMS:
        query = build_query(niche, domain, competitor)
        results = search_platform(query, max_results=6)
        if results:
            all_results.append(f"### {label} (query: {query[:80]}...)")
            for r in results:
                title = r.get("title", "")
                url = r.get("href", "")
                body = r.get("body", "")[:300]
                all_results.append(f"**{title}**\n{url}\n{body}\n")
        time.sleep(0.8)  # respect rate limits

    # General niche forum search (no site restriction)
    forum_query = f'"{niche}" forum site:community OR site:forum OR "ukbusinessforums" ({_PAIN_TERMS})'
    forum_results = search_platform(forum_query, max_results=5)
    if forum_results:
        all_results.append("### Niche Forums")
        for r in forum_results:
            title = r.get("title", "")
            url = r.get("href", "")
            body = r.get("body", "")[:300]
            all_results.append(f"**{title}**\n{url}\n{body}\n")

    return "\n".join(all_results) if all_results else "No search results returned."


def get_lead_count(segment: str) -> int:
    """Query Supabase for lead count in a segment, falling back to estimates."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return LEAD_BASE_SEGMENTS.get(segment.lower().replace(" ", "_"), 0)
    try:
        from supabase import create_client

        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        result = (
            client.table("leads")
            .select("id", count="exact")
            .ilike("category", f"%{segment}%")
            .execute()
        )
        return result.count or 0
    except Exception:
        return LEAD_BASE_SEGMENTS.get(segment.lower().replace(" ", "_"), 0)


def format_lead_counts() -> str:
    lines = ["## Lead Base Segments"]
    for segment, estimate in LEAD_BASE_SEGMENTS.items():
        count = get_lead_count(segment)
        lines.append(f"- **{segment.replace('_', ' ').title()}**: ~{count:,} leads")
    return "\n".join(lines)
