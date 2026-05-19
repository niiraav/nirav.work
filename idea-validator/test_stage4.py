#!/usr/bin/env python3
"""Tests for Stage 4 extractors: pricing tiers and unit economics."""

import pytest
import sys
import os

os.environ.setdefault("FIREWORKS_API_KEY", "test-key")
os.environ.setdefault("FIREWORKS_BASE_URL", "https://test.local")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents import extract_pricing_tiers, extract_unit_economics


class TestExtractPricingTiers:
    def test_em_dash_format(self):
        """Match **Tier — £29/mo**: description pattern."""
        text = """
**Free Tier — £0**: Self-service sign-up, basic patch test logging, 5 client records.
**Pro Tier — £29/month**: Unlimited clients, treatment history, SMS reminders.
**Enterprise — £99/mo**: Multi-location, analytics, priority support.
        """
        tiers = extract_pricing_tiers(text)
        assert len(tiers) >= 3
        assert tiers[0]["name"] == "Free Tier"
        assert tiers[0]["price_str"] == "£0"
        assert tiers[0]["price_value"] == 0.0
        assert tiers[0]["period"] == "month"
        assert tiers[1]["name"] == "Pro Tier"
        assert tiers[1]["price_str"] == "£29/month"
        assert tiers[1]["price_value"] == 29.0
        assert tiers[2]["name"] == "Enterprise"
        assert tiers[2]["price_str"] == "£99/mo"

    def test_year_period(self):
        """Detect yearly billing period."""
        text = "**Annual Plan — £199/yr**: Full year access with discount."
        tiers = extract_pricing_tiers(text)
        assert len(tiers) == 1
        assert tiers[0]["price_value"] == 199.0
        assert tiers[0]["period"] == "year"

    def test_one_time(self):
        """Detect one-time purchase."""
        text = "**Lifetime Deal — £499 one-time**: Pay once, use forever."
        tiers = extract_pricing_tiers(text)
        assert len(tiers) == 1
        assert tiers[0]["price_value"] == 499.0
        assert tiers[0]["period"] == "one-time"

    def test_fallback_format(self):
        """Match simpler 'Tier: £X (period)' fallback."""
        text = """
1. Starter (£9/mo): Basic features
2. Growth (£29/mo): Advanced features
        """
        tiers = extract_pricing_tiers(text)
        assert len(tiers) >= 2
        assert tiers[0]["price_value"] == 9.0
        assert tiers[0]["period"] == "mo"

    def test_skip_invalid(self):
        """Skip entries with no real price or name."""
        text = "Some random text without pricing tiers"
        tiers = extract_pricing_tiers(text)
        assert len(tiers) == 0

    def test_no_duplicates(self):
        """Don't extract duplicate tier names."""
        text = "**Pro — £29**: description.\n**Pro — £29**: same again."
        tiers = extract_pricing_tiers(text)
        assert len(tiers) == 1


class TestExtractUnitEconomics:
    def test_cac_ltv_margin(self):
        """Extract CAC, LTV, gross margin, payback."""
        text = """
Unit Economics:
- CAC: £35 (organic content + referral)
- LTV: £420 (Pro tier, 14-month avg lifetime)
- Gross Margin: 78%
- CAC Payback Period: 2.3 months
        """
        ue = extract_unit_economics(text)
        assert ue["cac"] == 35.0
        assert ue["ltv"] == 420.0
        assert ue["gross_margin"] == 78.0
        assert ue["payback_months"] == 2.3
        assert ue["verified"] is True
        assert ue["cac_tier"] == "safe"

    def test_cac_weak_zone(self):
        """CAC £75 triggers weak tier."""
        text = "Customer acquisition cost: £75 per customer"
        ue = extract_unit_economics(text)
        assert ue["cac"] == 75.0
        assert ue["cac_tier"] == "weak"
        assert ue["verified"] is True

    def test_cac_kill_zone(self):
        """CAC £120 triggers kill tier."""
        text = "CAC: £120"
        ue = extract_unit_economics(text)
        assert ue["cac"] == 120.0
        assert ue["cac_tier"] == "kill"
        assert ue["verified"] is True

    def test_no_numbers(self):
        """Handle text with no extractable metrics."""
        text = "The business model looks promising but needs more research."
        ue = extract_unit_economics(text)
        assert ue["cac"] is None
        assert ue["ltv"] is None
        assert ue["gross_margin"] is None
        assert ue["payback_months"] is None
        assert ue["verified"] is False
        assert ue["cac_tier"] is None

    def test_usd_currency(self):
        """Also match $ currency."""
        text = "CAC: $50, LTV: $600, gross margin: 65%"
        ue = extract_unit_economics(text)
        assert ue["cac"] == 50.0
        assert ue["ltv"] == 600.0
        assert ue["gross_margin"] == 65.0

    def test_comma_in_numbers(self):
        """Handle numbers with commas like £1,200."""
        text = "LTV: £1,200, CAC: £40"
        ue = extract_unit_economics(text)
        assert ue["ltv"] == 1200.0
        assert ue["cac"] == 40.0


class TestExtractPricingTiersWithMetaCommentary:
    def test_strip_meta(self):
        """Meta-commentary at top should be stripped before extraction."""
        text = """I need to think about this carefully. The user wants me to propose pricing.
**Starter — £9/mo**: Basic plan.
**Pro — £29/mo**: Advanced plan.
        """
        tiers = extract_pricing_tiers(text)
        assert len(tiers) >= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
