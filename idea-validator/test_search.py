#!/usr/bin/env python3
"""
Standalone search validator — run this BEFORE a pipeline stage to confirm
that queries return relevant results for your niche.

Usage:
  python test_search.py "Ecom HMRC MTD VAT Filing"
  python test_search.py "MOT Reminder SaaS for UK Garages"
  python test_search.py --query "HMRC MTD VAT software UK"   # test a raw query
"""

import argparse
import sys
from research import (
    search_pain_points,
    _get_broader_terms,
    _get_subreddits,
    _extract_keywords,
    search_ddg,
    format_reddit_results,
    format_search_results,
)


def _divider(title: str = ""):
    width = 70
    if title:
        pad = (width - len(title) - 2) // 2
        print("=" * pad + f" {title} " + "=" * pad)
    else:
        print("=" * width)


def test_niche(niche_name: str):
    print()
    _divider(f"SEARCH VALIDATION: {niche_name[:40]}")

    keywords = _extract_keywords(niche_name)
    broader = _get_broader_terms(niche_name)
    subreddits = _get_subreddits(niche_name)

    print(f"\nNiche:         {niche_name}")
    print(f"Keywords:      {keywords}")
    print(f"Broader terms: {broader}")
    print(f"Subreddits:    {subreddits}")
    print()

    _divider("RUNNING SEARCH")
    results = search_pain_points(niche_name)

    total = sum(len(v) for v in results.values())
    print(f"Total results: {total}")
    print()

    reddit_posts = results.get("reddit", [])
    _divider("REDDIT POSTS")
    if not reddit_posts:
        print("  (no results)")
    for i, post in enumerate(reddit_posts[:8], 1):
        pain = post.get("pain_score", 0)
        label = "🔥" if pain >= 3 else ("⚡" if pain >= 1 else "  ")
        print(f"  {label} {i}. [{post.get('subreddit','')}] {post.get('title','')[:100]}")
        print(f"       pain={pain}  score={post.get('score',0)}  comments={post.get('num_comments',0)}")
        if post.get("selftext"):
            print(f"       {post['selftext'][:150]}")
        for j, c in enumerate(post.get("top_comments", [])[:2], 1):
            print(f"       Comment {j}: {c[:120]}")
        print()

    for category in ["competitor_reviews", "competitor_landscape"]:
        items = results.get(category, [])
        _divider(category.upper().replace("_", " "))
        if not items:
            print("  (no results)")
        for i, item in enumerate(items, 1):
            title = item.get("title", "")
            href = item.get("href", "")
            body = item.get("body", "")
            if "Search error" in title or "bing.com/aclick" in href:
                continue
            print(f"  {i}. {title}")
            print(f"     {href}")
            if body:
                print(f"     {body[:200]}")
            print()

    _divider("FORMATTED OUTPUT (what agents see)")
    print(format_search_results(results))
    print()

    # Relevance check: flag results that look off-topic
    all_titles = " ".join(
        item.get("title", "") + " " + item.get("body", "")
        for cat in results.values()
        for item in cat
    ).lower()

    niche_lower = niche_name.lower()
    core_words = [w for w in niche_lower.split() if len(w) > 4]
    matched = [w for w in core_words if w in all_titles]
    coverage = len(matched) / len(core_words) if core_words else 0

    _divider("RELEVANCE SIGNAL")
    print(f"  Core words:  {core_words}")
    print(f"  Matched:     {matched}")
    print(f"  Coverage:    {coverage:.0%}")
    if coverage < 0.3:
        print("  ⚠️  LOW — results look off-topic. Fix _get_broader_terms() or queries.")
    elif coverage < 0.6:
        print("  ⚡ MEDIUM — some overlap but check results above for relevance.")
    else:
        print("  ✅ HIGH — looks on-topic.")
    print()


def test_raw_query(query: str):
    _divider(f"RAW QUERY: {query[:50]}")
    results = search_ddg(query, max_results=8)
    print(f"Results: {len(results)}\n")
    for i, r in enumerate(results, 1):
        print(f"  {i}. {r.get('title', '')}")
        print(f"     {r.get('href', '')}")
        body = r.get("body", "")
        if body:
            print(f"     {body[:200]}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Validate search queries for a niche")
    parser.add_argument("niche", nargs="?", help="Niche name to test")
    parser.add_argument("--query", "-q", help="Test a raw DuckDuckGo query directly")
    args = parser.parse_args()

    if args.query:
        test_raw_query(args.query)
    elif args.niche:
        test_niche(args.niche)
    else:
        # Default: run the three most commonly broken niches
        niches = [
            "Ecom HMRC MTD VAT Filing",
            "MOT Reminder SaaS for UK Independent Garages",
            "Digital Patch Test Logs for Independent Beauty Therapists",
        ]
        for n in niches:
            test_niche(n)
            print()


if __name__ == "__main__":
    main()
