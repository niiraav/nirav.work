import time
from typing import Dict, Optional
from duckduckgo_search import DDGS
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


# ---------------------------------------------------------------------------
# Lead count integration with Supabase
# ---------------------------------------------------------------------------

# Mapping from actual database category values → manifest segment keys
# Update this as the lead database grows and categories change
CATEGORY_TO_SEGMENT: Dict[str, str] = {
    # Trades
    "plumbing": "trades",
    "plumber": "trades",
    "plumbing supply store": "trades",
    "roofing contractor": "trades",
    "electrical": "trades",
    "construction": "trades",
    "cleaning": "trades",
    "window cleaning service": "trades",
    # Automotive
    "automotive": "automotive",
    "car repair": "automotive",
    "auto repair": "automotive",
    "mechanic": "automotive",
    # Beauty & Health
    "beauty": "beauty_health",
    "beauty salon": "beauty_health",
    "hair salon": "beauty_health",
    "dentist": "beauty_health",
    "dental clinic": "beauty_health",
    "cosmetic dentist": "beauty_health",
    "orthodontist": "beauty_health",
    # Food & Hospitality
    "hospitality": "food_hospitality",
    "restaurant": "food_hospitality",
    "cafe": "food_hospitality",
    "catering": "food_hospitality",
    # Professional Services
    "professional services": "professional_services",
    "real estate": "professional_services",
    "property management company": "professional_services",
    "finance": "professional_services",
    # Ecom / Retail
    "ecom": "ecom",
    "retail": "ecom",
    "e-commerce": "ecom",
    "online store": "ecom",
}

_LIVE_COUNTS: Dict[str, int] = {}


def _get_supabase_client():
    """Create a Supabase client if credentials are available."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


def get_lead_count(segment: str, use_cache: bool = True) -> int:
    """Query Supabase for lead count in a segment, falling back to estimates.
    
    Args:
        segment: Segment key (e.g. "beauty_health")
        use_cache: If True, return cached live count if available
    
    Returns:
        Lead count (live if Supabase connected, else manifest estimate)
    """
    normalized = segment.lower().replace(" ", "_")
    
    # Return cached live count if available
    if use_cache and normalized in _LIVE_COUNTS:
        return _LIVE_COUNTS[normalized]
    
    # Try Supabase query
    client = _get_supabase_client()
    if not client:
        return LEAD_BASE_SEGMENTS.get(normalized, 0)
    
    try:
        result = (
            client.table("leads")
            .select("id", count="exact")
            .ilike("category", f"%{segment}%")
            .execute()
        )
        count = result.count or 0
        _LIVE_COUNTS[normalized] = count
        return count
    except Exception:
        return LEAD_BASE_SEGMENTS.get(normalized, 0)


def refresh_lead_counts(segments: list[str] = None) -> Dict[str, int]:
    """Refresh live lead counts from Supabase for all configured segments.
    
    Fetches all lead categories from Supabase, maps them to manifest segments,
    and aggregates counts. Segments with no matching live leads fall back to
    manifest estimates.
    
    Args:
        segments: List of segment keys to refresh. Defaults to all LEAD_BASE_SEGMENTS keys.
    
    Returns:
        Dict mapping segment -> live count (or estimate if Supabase unavailable)
    """
    global _LIVE_COUNTS
    
    if segments is None:
        segments = list(LEAD_BASE_SEGMENTS.keys())
    
    client = _get_supabase_client()
    if not client:
        # No Supabase connection — use estimates
        _LIVE_COUNTS = dict(LEAD_BASE_SEGMENTS)
        print("  ⚠️  Supabase not configured — using manifest estimates for lead counts")
        return dict(_LIVE_COUNTS)
    
    refreshed: Dict[str, int] = {}
    print("  🔌 Querying Supabase for live lead counts...")
    
    try:
        # Fetch all categories in one query
        result = client.table("leads").select("category").not_.is_("category", "null").execute()
        rows = result.data or []
        
        # Aggregate by mapped segment
        category_counts: Dict[str, int] = {}
        for row in rows:
            cat = (row.get("category") or "").lower().strip()
            if not cat:
                continue
            segment = CATEGORY_TO_SEGMENT.get(cat)
            if segment:
                category_counts[segment] = category_counts.get(segment, 0) + 1
        
        # Assign counts to requested segments
        for segment in segments:
            normalized = segment.lower().replace(" ", "_")
            count = category_counts.get(normalized, 0)
            estimate = LEAD_BASE_SEGMENTS.get(normalized, 0)
            
            if count > 0:
                refreshed[normalized] = count
                _LIVE_COUNTS[normalized] = count
                delta = count - estimate
                delta_str = f" (+{delta})" if delta > 0 else f" ({delta})" if delta < 0 else ""
                print(f"    - {normalized}: {count:,} leads{delta_str}")
            else:
                # No matching categories found — use estimate
                refreshed[normalized] = estimate
                _LIVE_COUNTS[normalized] = estimate
                print(f"    - {normalized}: {estimate:,} leads (estimate — no matching categories in DB)")
        
        # Report unmapped categories for discovery
        unmapped = set()
        for row in rows:
            cat = (row.get("category") or "").lower().strip()
            if cat and cat not in CATEGORY_TO_SEGMENT:
                unmapped.add(cat)
        if unmapped:
            print(f"\n  💡 Unmapped categories ({len(unmapped)}): {', '.join(sorted(unmapped)[:10])}")
            if len(unmapped) > 10:
                print(f"     ... and {len(unmapped) - 10} more")
        
    except Exception as e:
        # Query failed — fall back to estimates for all
        print(f"  ⚠️  Supabase query failed: {e}")
        for segment in segments:
            normalized = segment.lower().replace(" ", "_")
            estimate = LEAD_BASE_SEGMENTS.get(normalized, 0)
            refreshed[normalized] = estimate
            _LIVE_COUNTS[normalized] = estimate
            print(f"    - {normalized}: {estimate:,} leads (estimate)")
    
    print(f"  ✅ Live counts refreshed for {len(refreshed)} segments")
    return refreshed


def get_all_lead_counts() -> Dict[str, int]:
    """Return the best available lead counts (live if cached, else estimates)."""
    if _LIVE_COUNTS:
        return dict(_LIVE_COUNTS)
    return dict(LEAD_BASE_SEGMENTS)


def format_lead_counts(refreshed_counts: Optional[Dict[str, int]] = None) -> str:
    """Format lead counts as markdown. Uses refreshed counts if provided, else cached/live."""
    counts = refreshed_counts if refreshed_counts is not None else get_all_lead_counts()
    lines = ["## Lead Base Segments"]
    total = 0
    for segment, count in sorted(counts.items()):
        total += count
        lines.append(f"- **{segment.replace('_', ' ').title()}**: ~{count:,} leads")
    lines.append(f"\n**Total addressable leads**: ~{total:,}")
    return "\n".join(lines)


def inject_lead_counts_into_manifest(manifest: dict) -> dict:
    """Update manifest lead_segments with live Supabase counts.
    
    Returns a new manifest dict with refreshed counts. Non-destructive —
    preserves original as manifest['_original_lead_segments'].
    """
    refreshed = refresh_lead_counts()
    if "_original_lead_segments" not in manifest:
        manifest["_original_lead_segments"] = dict(manifest.get("lead_segments", {}))
    manifest["lead_segments"] = {
        k: refreshed.get(k.lower().replace(" ", "_"), v)
        for k, v in manifest.get("lead_segments", {}).items()
    }
    return manifest
