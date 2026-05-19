"""
research.py — Web search + Reddit API module for Stage 2 evidence gathering.

Sources (ranked by signal quality):
  1. Reddit API   ★★★★★  Authentic first-person pain language, no ads, direct quotes
  2. DDGS reviews ★★★★☆  Competitor complaint pages (G2, Trustpilot, ICAEW)
  3. DDGS signals ★★★☆☆  Broader industry pain keywords
  4. DDGS landing ★★☆☆☆  Competitor landscape (who exists)

Reddit strategy:
  - Map niche → relevant subreddits (UK-focused first)
  - Search each subreddit for pain-signal keywords
  - Score posts by pain language density
  - Fetch top 3 comments from the highest-scoring posts
  - Return structured evidence for agents
"""

import re
import time
import requests
from typing import List, Dict, Any, Optional


# ---------------------------------------------------------------------------
# Reddit configuration
# ---------------------------------------------------------------------------

_REDDIT_USER_AGENT = "idea-validator/1.0 (startup research tool; contact: research@idea-validator.local)"
_REDDIT_BASE = "https://www.reddit.com"
_REDDIT_DELAY = 1.1  # seconds between requests (public API: ~60/min)

# Pain-signal keywords — any of these in a post/comment raises its score
_PAIN_KEYWORDS = [
    "frustrated", "frustrating", "hate", "annoying", "nightmare",
    "broken", "waste of time", "wasting time", "sick of", "tired of",
    "struggling", "can't figure out", "doesn't work", "doesn't do",
    "spreadsheet", "excel", "manual", "still using", "pen and paper",
    "error", "failed", "confusing", "complicated", "overpriced",
    "need help", "anyone else", "how do you", "how do I", "what do you use",
    "alternative", "switch from", "switched from", "gave up", "ditched",
    "problem", "issue", "bug", "pain point", "slow", "clunky", "terrible",
    "awful", "disaster", "mess", "chaotic", "overwhelming", "lost",
]

# Subreddits that are general communities / entertainment — filter these from global search
_BLOCKLIST_SUBREDDITS = {
    "BestofRedditorUpdates", "tifu", "AITA", "AmItheAsshole", "relationship_advice",
    "legaladvice", "LegalAdviceUK", "AskReddit", "NoStupidQuestions", "explainlikeimfive",
    "mildlyinfuriating", "funny", "pics", "videos", "news", "worldnews",
    "personalfinance",  # US-only finance advice
}

# Niche category → subreddits (UK-relevant first, then generic)
_SUBREDDIT_MAP: Dict[str, List[str]] = {
    "tax":            ["TaxUK", "ContractorUK", "smallbusinessuk", "UKPersonalFinance", "Accounting"],
    "vat":            ["TaxUK", "ContractorUK", "smallbusinessuk", "selfemployed", "UKBusiness"],
    "hmrc":           ["TaxUK", "ContractorUK", "smallbusinessuk", "UKPersonalFinance"],
    "mtd":            ["TaxUK", "ContractorUK", "smallbusinessuk", "Accounting"],
    "accounting":     ["Accounting", "smallbusinessuk", "ContractorUK", "freelance"],
    "bookkeeping":    ["Accounting", "smallbusinessuk", "freelance"],
    "ecom":           ["ecommerce", "shopify", "AmazonSeller", "smallbusinessuk", "Entrepreneur"],
    "ecommerce":      ["ecommerce", "shopify", "AmazonSeller", "smallbusinessuk"],
    "shopify":        ["shopify", "ecommerce", "smallbusiness"],
    "amazon":         ["AmazonSeller", "FulfillmentByAmazon", "ecommerce"],
    "automotive":     ["MechanicAdvice", "AutoRepair", "CarMaintenance", "smallbusinessuk"],
    "garage":         ["MechanicAdvice", "AutoRepair", "CarMaintenance", "smallbusinessuk"],
    "mot":            ["CarMaintenance", "MechanicAdvice", "smallbusinessuk", "TaxUK"],
    "beauty":         ["Hairstylist", "esthetics", "MakeupArtists", "smallbusiness"],
    "salon":          ["Hairstylist", "esthetics", "smallbusiness"],
    "therapist":      ["esthetics", "Hairstylist", "smallbusiness"],
    "food":           ["KitchenConfidential", "restaurantowners", "FoodService", "smallbusiness"],
    "restaurant":     ["restaurantowners", "KitchenConfidential", "FoodService"],
    "hospitality":    ["restaurantowners", "KitchenConfidential", "FoodService", "smallbusiness"],
    "trades":         ["Construction", "Plumbing", "HVAC", "smallbusiness", "HomeImprovement"],
    "builder":        ["Construction", "DIY", "smallbusiness"],
    "plumber":        ["Plumbing", "HVAC", "smallbusiness"],
    "construction":   ["Construction", "HomeImprovement", "smallbusiness"],
    "professional":   ["consulting", "freelance", "smallbusiness", "Entrepreneur"],
    "consulting":     ["consulting", "freelance", "smallbusiness"],
    "freelance":      ["freelance", "consulting", "smallbusiness"],
}

_DEFAULT_SUBREDDITS = ["smallbusiness", "Entrepreneur", "startups", "selfemployed"]


# ---------------------------------------------------------------------------
# Reddit helpers
# ---------------------------------------------------------------------------

def _get_subreddits(niche_name: str) -> List[str]:
    """Map a niche name to a deduplicated list of relevant subreddits."""
    lower = niche_name.lower()
    subreddits: List[str] = []
    seen = set()
    for keyword, subs in _SUBREDDIT_MAP.items():
        if keyword in lower:
            for s in subs:
                if s not in seen:
                    seen.add(s)
                    subreddits.append(s)
    # Always add UK-generic fallbacks
    for s in ["smallbusinessuk", "UKBusiness"]:
        if s not in seen:
            subreddits.append(s)
            seen.add(s)
    if not subreddits:
        subreddits = _DEFAULT_SUBREDDITS[:]
    return subreddits[:6]  # cap at 6 subreddits per niche


def _score_pain(text: str) -> int:
    """Count pain-signal keywords in a block of text. Higher = more pain."""
    lower = text.lower()
    return sum(1 for kw in _PAIN_KEYWORDS if kw in lower)


def _reddit_get(url: str, params: Dict = None) -> Optional[Dict]:
    """Single Reddit API GET with User-Agent header. Returns parsed JSON or None."""
    try:
        r = requests.get(
            url,
            params=params or {},
            headers={"User-Agent": _REDDIT_USER_AGENT},
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def _search_subreddit(subreddit: str, query: str, limit: int = 10) -> List[Dict]:
    """Search a specific subreddit via Reddit's public JSON API.
    Returns list of post dicts with title, selftext, url, score, pain_score, id."""
    url = f"{_REDDIT_BASE}/r/{subreddit}/search.json"
    params = {"q": query, "restrict_sr": "1", "sort": "relevance", "t": "year", "limit": limit}
    data = _reddit_get(url, params)
    time.sleep(_REDDIT_DELAY)
    if not data:
        return []
    posts = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        title = d.get("title", "")
        selftext = d.get("selftext", "")[:600]
        combined = f"{title} {selftext}"
        posts.append({
            "id": d.get("id", ""),
            "subreddit": d.get("subreddit_name_prefixed", f"r/{subreddit}"),
            "title": title[:200],
            "selftext": selftext,
            "url": f"https://reddit.com{d.get('permalink', '')}",
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "pain_score": _score_pain(combined),
        })
    return posts


def _search_reddit_global(query: str, limit: int = 10) -> List[Dict]:
    """Search all of Reddit (no subreddit restriction)."""
    url = f"{_REDDIT_BASE}/search.json"
    params = {"q": query, "sort": "relevance", "t": "year", "limit": limit}
    data = _reddit_get(url, params)
    time.sleep(_REDDIT_DELAY)
    if not data:
        return []
    posts = []
    for child in data.get("data", {}).get("children", []):
        d = child.get("data", {})
        title = d.get("title", "")
        selftext = d.get("selftext", "")[:600]
        combined = f"{title} {selftext}"
        posts.append({
            "id": d.get("id", ""),
            "subreddit": d.get("subreddit_name_prefixed", "r/?"),
            "title": title[:200],
            "selftext": selftext,
            "url": f"https://reddit.com{d.get('permalink', '')}",
            "score": d.get("score", 0),
            "num_comments": d.get("num_comments", 0),
            "pain_score": _score_pain(combined),
        })
    return posts


def _fetch_top_comments(post_id: str, subreddit: str, max_comments: int = 5) -> List[str]:
    """Fetch the top comments for a Reddit post. Returns list of comment body strings."""
    sub = subreddit.lstrip("r/")
    url = f"{_REDDIT_BASE}/r/{sub}/comments/{post_id}.json"
    data = _reddit_get(url, {"limit": max_comments, "sort": "best", "depth": 1})
    time.sleep(_REDDIT_DELAY)
    if not data or not isinstance(data, list) or len(data) < 2:
        return []
    comments = []
    for child in data[1].get("data", {}).get("children", []):
        d = child.get("data", {})
        body = d.get("body", "").strip()
        if body and body != "[deleted]" and body != "[removed]" and len(body) > 20:
            comments.append(body[:400])
            if len(comments) >= max_comments:
                break
    return comments


def search_reddit_pain_points(niche_name: str, max_posts: int = 10) -> List[Dict[str, Any]]:
    """Main Reddit search function for Stage 2 pain point evidence.

    Strategy:
      1. Map niche → subreddits
      2. Search each subreddit with pain-specific query
      3. Also run a global Reddit search for broad coverage
      4. Score all posts by pain keyword density
      5. Fetch top comments for the top 3 posts
      6. Return results sorted by pain score descending

    Returns list of post dicts with: title, subreddit, url, selftext,
    pain_score, score (upvotes), top_comments.
    """
    subreddits = _get_subreddits(niche_name)
    broader_terms = _get_broader_terms(niche_name)
    primary_kw = broader_terms[0] if broader_terms else niche_name[:50]

    # Build pain-focused query (no quotes — broader matching)
    query = f"{primary_kw} problem frustrating manual spreadsheet"

    print(f"   Reddit: searching subreddits {subreddits[:4]} + global...")

    all_posts: List[Dict] = []
    seen_ids: set = set()

    # Search top subreddits
    for sub in subreddits[:4]:
        posts = _search_subreddit(sub, query, limit=8)
        for p in posts:
            if p["id"] and p["id"] not in seen_ids:
                seen_ids.add(p["id"])
                all_posts.append(p)

    # Global fallback search — exclude off-topic subreddits
    global_posts = _search_reddit_global(query, limit=10)
    for p in global_posts:
        sub_name = p.get("subreddit", "").lstrip("r/")
        if sub_name in _BLOCKLIST_SUBREDDITS:
            continue
        if p["id"] and p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            all_posts.append(p)

    # Sort by pain score descending, then by Reddit score
    all_posts.sort(key=lambda p: (p["pain_score"], p["score"]), reverse=True)
    top_posts = all_posts[:max_posts]

    # Fetch comments for the top 3 pain-rich posts
    for post in top_posts[:3]:
        if post.get("id") and post.get("subreddit"):
            post["top_comments"] = _fetch_top_comments(post["id"], post["subreddit"], max_comments=4)
        else:
            post["top_comments"] = []

    # Fill remaining posts with empty comments
    for post in top_posts[3:]:
        post.setdefault("top_comments", [])

    return top_posts


def format_reddit_results(posts: List[Dict[str, Any]]) -> str:
    """Format Reddit posts + comments into markdown for agent prompts.
    Only includes posts with pain_score >= 1 to filter generic noise."""
    if not posts:
        return "## Reddit Evidence\n*(No relevant posts found)*"

    # Filter to posts with at least one pain keyword match
    relevant = [p for p in posts if p.get("pain_score", 0) >= 1]
    if not relevant:
        relevant = posts  # fallback: show all if nothing scored

    lines = ["## Reddit Evidence (Direct User Pain Signals)"]
    for i, post in enumerate(relevant[:8], 1):
        title = post.get("title", "")
        url = post.get("url", "")
        subreddit = post.get("subreddit", "")
        selftext = post.get("selftext", "").strip()
        pain_score = post.get("pain_score", 0)
        comments = post.get("top_comments", [])

        signal_label = "🔥" if pain_score >= 3 else ("⚡" if pain_score >= 1 else "")
        lines.append(f"\n**{i}. {title[:120]}** {signal_label}")
        lines.append(f"   Source: {subreddit} — {url}")

        if selftext:
            # Sanitize and trim
            clean = re.sub(r'\s+', ' ', selftext.strip())
            lines.append(f"   > {clean[:250]}")

        for j, comment in enumerate(comments[:2], 1):
            clean_c = re.sub(r'\s+', ' ', comment.strip())
            lines.append(f"   Comment {j}: {clean_c[:200]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# DDGS helpers (retained for competitor reviews + landscape)
# ---------------------------------------------------------------------------

def search_ddg(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Run a DuckDuckGo search via ddgs and return top results."""
    try:
        from ddgs import DDGS
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            return [
                {
                    "title": r.get("title", "")[:120],
                    "href": r.get("href", ""),
                    "body": r.get("body", "")[:300],
                }
                for r in results
            ]
    except Exception as e:
        return [{"title": f"Search error: {e}", "href": "", "body": ""}]


def _extract_keywords(niche_name: str) -> List[str]:
    """Extract shorter search keywords from a long niche name."""
    filler = {
        "for", "and", "or", "the", "a", "an", "in", "on", "at", "to", "of",
        "digital", "automated", "independent", "small", "uk", "smb", "saas",
        "prediction", "prevention", "reconciliation", "management",
    }
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", niche_name)]
    keywords = [w for w in words if w not in filler and len(w) > 3]
    if len(keywords) >= 3:
        return [" ".join(keywords[:3]), " ".join(keywords[2:5])]
    return [" ".join(keywords)] if keywords else [niche_name[:50]]


def _get_broader_terms(niche_name: str) -> List[str]:
    """Map a niche name to broader industry search terms for DDGS queries."""
    lower = niche_name.lower()
    if "beauty" in lower and ("salon" in lower or "therapist" in lower or "treatment" in lower):
        return [
            "beauty salon software",
            "salon client records digital",
            "beauty therapist insurance compliance UK",
            "salon pen paper problem",
        ]
    if "food" in lower or "restaurant" in lower or "hospitality" in lower:
        return [
            "restaurant software UK",
            "food business compliance software",
            "restaurant paperwork problem",
            "small food business admin",
        ]
    if "vat" in lower or "hmrc" in lower or "mtd" in lower or "tax" in lower or "accounting" in lower or "bookkeeping" in lower:
        return [
            "HMRC MTD VAT software UK",
            "ecommerce VAT filing software",
            "small business VAT compliance UK",
            "MTD Making Tax Digital complaints",
        ]
    if "fashion" in lower or "retail" in lower or "ecommerce" in lower or "e-commerce" in lower or "ecom" in lower:
        return [
            "ecommerce operations software UK",
            "online retailer admin problem",
            "small ecommerce business pain",
            "shopify seller problems UK",
        ]
    if "trade" in lower or "builder" in lower or "construction" in lower:
        return [
            "tradesman software UK",
            "construction business admin",
            "builder paperwork problem",
            "trades compliance software",
        ]
    if "automotive" in lower or "garage" in lower or "mot" in lower or "car" in lower:
        return [
            "garage software UK",
            "automotive workshop management",
            "MOT garage admin problem",
            "car repair shop software",
        ]
    keywords = _extract_keywords(niche_name)
    return [keywords[0] if keywords else niche_name[:50]]


def search_competitor_reviews(niche_keywords: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search competitor review sites for complaint signals (G2, Trustpilot, ICAEW)."""
    queries = [
        f'"{niche_keywords}" review complaint problem',
        f'"{niche_keywords}" g2 OR trustpilot OR capterra',
        f'"{niche_keywords}" software broken OR frustrating OR "waste of time"',
    ]
    all_results = []
    for q in queries:
        all_results.extend(search_ddg(q, max_results=max_results))
    return all_results[:max_results]


def search_competitor_landscape(niche_keywords: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Discover who the competitors are in this space."""
    queries = [
        f'best {niche_keywords} software 2024 2025',
        f'{niche_keywords} alternative OR competitor',
        f'{niche_keywords} software OR app OR platform comparison',
    ]
    all_results = []
    for q in queries:
        all_results.extend(search_ddg(q, max_results=max_results))
    return all_results[:max_results]


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def search_pain_points(niche_name: str) -> Dict[str, Any]:
    """Run all evidence searches for Stage 2.

    Returns a dict with:
      - 'reddit'              → list of Reddit post dicts (primary pain signal)
      - 'competitor_reviews'  → DDGS results from G2/Trustpilot
      - 'competitor_landscape'→ DDGS results for competitor discovery
    """
    broader_terms = _get_broader_terms(niche_name)
    primary_kw = broader_terms[0]
    secondary_kw = broader_terms[1] if len(broader_terms) > 1 else primary_kw

    # Reddit is the primary source — runs first
    reddit_posts = search_reddit_pain_points(niche_name, max_posts=10)

    results = {
        "reddit": reddit_posts,
        "competitor_reviews": search_competitor_reviews(primary_kw, max_results=5),
        "competitor_landscape": search_competitor_landscape(secondary_kw, max_results=5),
    }
    return results


def format_search_results(results: Dict[str, Any]) -> str:
    """Format all search results into a single markdown document for agent prompts."""
    sections = []

    # Reddit section (primary — show first)
    reddit_posts = results.get("reddit", [])
    if isinstance(reddit_posts, list) and reddit_posts and isinstance(reddit_posts[0], dict) and "title" in reddit_posts[0]:
        sections.append(format_reddit_results(reddit_posts))
    else:
        sections.append("## Reddit Evidence\n*(No results)*")

    # DDGS sections
    for category in ["competitor_reviews", "competitor_landscape"]:
        items = results.get(category, [])
        if not items:
            continue
        label = category.upper().replace("_", " ")
        lines = [f"\n## {label}"]
        for i, item in enumerate(items[:4], 1):
            title = item.get("title", "Untitled")
            href = item.get("href", "")
            body = item.get("body", "")
            # Skip error results and ad URLs
            if "Search error" in title or "bing.com/aclick" in href or not href:
                continue
            lines.append(f"{i}. **{title}** — {href}")
            if body:
                body_plain = re.sub(r'[#*_`\[\]]', ' ', body).strip()
                body_plain = re.sub(r'\s+', ' ', body_plain)
                lines.append(f"   > {body_plain[:180]}")
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def search_for_kill_condition(kill_condition: str, niche_keywords: str) -> List[Dict[str, str]]:
    """Search for evidence about a specific kill condition."""
    query = f'"{niche_keywords}" {kill_condition} UK'
    return search_ddg(query, max_results=5)
