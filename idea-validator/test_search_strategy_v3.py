#!/usr/bin/env python3
"""
Test script v3 — focused search strategy with competitor names,
industry bodies, and specific pain keywords.
"""

from research import search_ddg

NICHE = "Digital Patch Test & Treatment Logs for Independent Beauty Therapists"

# Competitor names known in UK salon software
COMPETITORS = [
    "Phorest salon software",
    "SalonIQ",
    "Timely salon",
    "Fresha salon",
    "Treatwell business",
    "iSalon",
    "Salon Tracker",
]

# UK beauty industry bodies
BODIES = [
    "HABIA beauty therapist requirements",
    "Beauty Guild insurance patch test",
    "BABTAC treatment records",
    "NHBF salon compliance UK",
]

# Specific pain keywords
PAIN_KEYWORDS = [
    "beauty salon client record keeping problem",
    "digital consent form beauty treatment UK",
    "salon paperwork time consuming",
    "beauty therapist insurance claim rejected record",
    "paper treatment log vs digital salon",
]

print(f"\n{'='*70}")
print(f"  SEARCH STRATEGY TEST v3: {NICHE}")
print(f"{'='*70}\n")

# ---------------------------------------------------------------------------
# Test A: Competitor review signals (highest value)
# ---------------------------------------------------------------------------
print("━" * 70)
print("TEST A: Competitor review signals (Trustpilot / G2 / Capterra)")
print("━" * 70)

for comp in COMPETITORS[:4]:
    q = f'"{comp}" review problem OR complaint OR broken'
    results = search_ddg(q, max_results=3)
    print(f"\n  Competitor: '{comp}' → {len(results)} results")
    for i, r in enumerate(results[:2], 1):
        title = r.get("title", "")[:65]
        body = r.get("body", "")[:80]
        print(f"    {i}. {title}")
        if body:
            print(f"       {body[:60]}...")

# ---------------------------------------------------------------------------
# Test B: Industry body + compliance signals
# ---------------------------------------------------------------------------
print(f"\n\n{'━'*70}")
print("TEST B: Industry body + compliance signals")
print("━" * 70)

for body in BODIES[:3]:
    q = f'"{body}" requirement OR must OR compulsory OR record'
    results = search_ddg(q, max_results=3)
    print(f"\n  Body: '{body}' → {len(results)} results")
    for i, r in enumerate(results[:2], 1):
        title = r.get("title", "")[:65]
        print(f"    {i}. {title}")

# ---------------------------------------------------------------------------
# Test C: Specific pain keywords
# ---------------------------------------------------------------------------
print(f"\n\n{'━'*70}")
print("TEST C: Specific pain keywords")
print("━" * 70)

for kw in PAIN_KEYWORDS[:4]:
    results = search_ddg(kw, max_results=3)
    print(f"\n  Keyword: '{kw}' → {len(results)} results")
    for i, r in enumerate(results[:2], 1):
        title = r.get("title", "")[:65]
        body = r.get("body", "")[:80]
        print(f"    {i}. {title}")
        if body:
            print(f"       {body[:60]}...")

# ---------------------------------------------------------------------------
# Test D: Forum/industry site searches
# ---------------------------------------------------------------------------
print(f"\n\n{'━'*70}")
print("TEST D: Forum / industry site searches")
print("━" * 70)

forum_queries = [
    'site:salongeek.com OR site:hairdressersjournal.com "client records" OR "insurance"',
    'site:professionalbeauty.co.uk OR site:hji.co.uk "digital" OR "software" salon',
    'site:salonbusiness.co.uk OR site:beautymatter.com "patch test" OR "consent"',
]
for q in forum_queries:
    results = search_ddg(q, max_results=3)
    print(f"\n  Query: '{q[:55]}...' → {len(results)} results")
    for i, r in enumerate(results[:2], 1):
        title = r.get("title", "")[:65]
        print(f"    {i}. {title}")

print(f"\n{'='*70}\n")
