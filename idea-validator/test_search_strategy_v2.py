#!/usr/bin/env python3
"""
Test script v2 — improved search strategy with keyword extraction and
better subreddit targeting.
"""

from research import search_ddg
from ddgs import DDGS
import requests

NICHE = "Digital Patch Test & Treatment Logs for Independent Beauty Therapists"

# Extract shorter search keywords from the niche name
# Don't search the full sentence — search the core concepts
KEYWORDS = [
    "beauty salon patch test digital",
    "beauty therapist client records UK",
    "salon software insurance requirements",
    "independent beauty therapist compliance UK",
]

# Better subreddits to target
SUBREDDITS = [
    "BeautyProfessionals",
    "HairStylist",
    "nails",
    "smallbusiness",
    "UKBusiness",
    "beauty",
]

print(f"\n{'='*70}")
print(f"  SEARCH STRATEGY TEST v2: {NICHE}")
print(f"{'='*70}\n")

# ---------------------------------------------------------------------------
# Test A: Reddit site search with extracted keywords
# ---------------------------------------------------------------------------
print("━" * 70)
print("TEST A: Reddit site search with extracted keywords")
print("━" * 70)

for kw in KEYWORDS:
    q = f'site:reddit.com "{kw}" OR "beauty salon" OR "therapist"'
    results = search_ddg(q, max_results=3)
    print(f"\n  Keyword: '{kw}' → {len(results)} results")
    for i, r in enumerate(results[:2], 1):
        title = r.get("title", "")[:60]
        body = r.get("body", "")[:100]
        print(f"    {i}. {title}")
        if body:
            print(f"       {body[:80]}...")

# ---------------------------------------------------------------------------
# Test B: Competitor landscape via G2/Capterra
# ---------------------------------------------------------------------------
print(f"\n\n{'━'*70}")
print("TEST B: Competitor landscape (G2/Capterra)")
print("━" * 70)

competitor_queries = [
    'site:g2.com "salon software" OR "spa software" OR "beauty salon management"',
    'site:capterra.com "salon software" UK',
    'site:trustpilot.com "salon software" review',
]
for q in competitor_queries:
    results = search_ddg(q, max_results=3)
    print(f"\n  Query: '{q[:50]}...' → {len(results)} results")
    for i, r in enumerate(results[:2], 1):
        title = r.get("title", "")[:60]
        print(f"    {i}. {title}")

# ---------------------------------------------------------------------------
# Test C: Reddit API direct search on relevant subreddits
# ---------------------------------------------------------------------------
print(f"\n\n{'━'*70}")
print("TEST C: Reddit API direct search on targeted subreddits")
print("━" * 70)

reddit_queries = [
    "insurance requirements beauty therapist",
    "client records paper vs digital",
    "patch test consent form",
]
for subreddit in SUBREDDITS[:3]:  # Test first 3
    for q in reddit_queries[:2]:  # Test first 2 queries
        try:
            url = f"https://www.reddit.com/r/{subreddit}/search.json"
            r = requests.get(
                url,
                params={"q": q, "sort": "relevance", "limit": 3},
                headers={"User-Agent": "idea-validator/1.0"},
                timeout=10,
            )
            if r.status_code == 200:
                data = r.json()
                posts = data.get("data", {}).get("children", [])
                if posts:
                    print(f"\n  r/{subreddit} | '{q}' → {len(posts)} posts")
                    for post in posts[:1]:
                        title = post.get("data", {}).get("title", "Untitled")[:60]
                        print(f"    - {title}")
            else:
                print(f"\n  r/{subreddit} | '{q}' → HTTP {r.status_code}")
        except Exception as e:
            print(f"\n  r/{subreddit} | '{q}' → Error: {e}")

# ---------------------------------------------------------------------------
# Test D: UK-specific regulatory/compliance search
# ---------------------------------------------------------------------------
print(f"\n\n{'━'*70}")
print("TEST D: UK regulatory/compliance sources")
print("━" * 70)

reg_queries = [
    'site:gov.uk "beauty therapist" insurance requirement',
    'site:hse.gov.uk "beauty salon" risk assessment',
    'site:ctpb.co.uk OR site:habia.org "patch test" consent',
]
for q in reg_queries:
    results = search_ddg(q, max_results=3)
    print(f"\n  Query: '{q[:50]}...' → {len(results)} results")
    for i, r in enumerate(results[:2], 1):
        title = r.get("title", "")[:60]
        print(f"    {i}. {title}")

print(f"\n{'='*70}\n")
