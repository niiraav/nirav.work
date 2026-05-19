#!/usr/bin/env python3
"""Tests for Stage 5 extractors: sprint plan extraction and final report generation."""

import pytest
import sys
import os

os.environ.setdefault("FIREWORKS_API_KEY", "test-key")
os.environ.setdefault("FIREWORKS_BASE_URL", "https://test.local")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agents import extract_sprint_plan
from orchestrator import generate_final_report


class TestExtractSprintPlan:
    def test_experiment_block_format(self):
        """Extract experiments from **Experiment N: Name** blocks."""
        text = """
**Experiment 1: Cold Email Outreach Test**
Hypothesis: 20% of beauty therapists will respond to a cold email about patch test digitisation.
Metric: Response rate from 50 targeted emails.
Success criteria: ≥10% response rate.
Duration: 7 days.

**Experiment 2: Landing Page Smoke Test**
Hypothesis: Therapists will click "Book a demo" at £29/mo pricing.
Metric: Click-through rate on pricing page.
Success criteria: ≥5% CTR.
Duration: 14 days.
        """
        experiments = extract_sprint_plan(text)
        assert len(experiments) == 2
        assert "Cold Email Outreach Test" in experiments[0]["name"]
        assert "20%" in experiments[0]["hypothesis"]
        assert "Response rate" in experiments[0]["metric"]
        assert "10%" in experiments[0]["success_criteria"]
        assert "7 days" in experiments[0]["duration"]
        
        assert "Landing Page Smoke Test" in experiments[1]["name"]
        assert "£29/mo" in experiments[1]["hypothesis"]

    def test_simple_numbered_format(self):
        """Extract from simple numbered list with dash separator."""
        text = """
1. **Competitor Review Deep-Dive** — Read 50 G2/Trustpilot reviews for competitors. Hypothesis: 30% mention paper-based records pain. Metric: % of reviews mentioning 'paper' or 'manual'. Success: ≥20% mention pain. Duration: 3 days.
2. **Waitlist Signup Test** — Put up a landing page with pricing. Hypothesis: 50 signups in 14 days. Metric: Number of email signups. Success: ≥25 signups. Duration: 14 days.
        """
        experiments = extract_sprint_plan(text)
        assert len(experiments) >= 1
        assert "Competitor Review Deep-Dive" in experiments[0]["name"] or "Waitlist Signup Test" in experiments[0]["name"]

    def test_no_experiments(self):
        """Handle text with no experiments."""
        text = "Some random discussion without structured experiments."
        experiments = extract_sprint_plan(text)
        assert len(experiments) == 0

    def test_max_five_experiments(self):
        """Never return more than 5 experiments."""
        text = "\n".join([
            f"**Experiment {i}: Test {i}**\nHypothesis: H{i}.\nMetric: M{i}.\nSuccess: S{i}.\nDuration: {i} days."
            for i in range(1, 10)
        ])
        experiments = extract_sprint_plan(text)
        assert len(experiments) == 5

    def test_dedupe_experiments(self):
        """Don't return duplicate experiment names."""
        text = """
**Experiment 1: Same Name**
Hypothesis: H1.

**Experiment 2: Same Name**
Hypothesis: H2.
        """
        experiments = extract_sprint_plan(text)
        assert len(experiments) == 1

    def test_hypothesis_only_fallback(self):
        """If body has hypothesis keyword but no structured fields, still capture."""
        text = """
1. **Survey 50 Therapists** — Hypothesis: 40% currently use paper records and would pay for digital. No other structured fields.
        """
        experiments = extract_sprint_plan(text)
        assert len(experiments) >= 1
        assert "Survey 50 Therapists" in experiments[0]["name"]


class TestGenerateFinalReport:
    def test_complete_session(self):
        """Generate report with all stages approved."""
        session = {
            "session_id": "test_session_123",
            "manifest": {"budget_ceiling": {"monthly_burn": 5000, "max_cac": 50}, "timeline_months": 6},
            "approved_niche": "Digital Patch Test Logs for Beauty Therapists",
            "approved_pain_point": "Paper records are unorganized and create insurance liability",
            "approved_solution": "Template-Based Compliance SaaS",
            "approved_business_model": {
                "pricing_tiers": [
                    {"name": "Free", "price_str": "£0", "period": "month", "price_value": 0},
                    {"name": "Pro", "price_str": "£29/mo", "period": "month", "price_value": 29},
                ],
                "unit_economics": {
                    "cac": 35.0,
                    "ltv": 420.0,
                    "gross_margin": 78.0,
                    "payback_months": 2.3,
                    "cac_tier": "safe",
                    "verified": True,
                },
                "cac_tier": "safe",
                "cac_kill_triggered": False,
            },
            "stages": {
                "1": {"status": "gate"},
                "2": {"status": "gate"},
                "3": {"status": "gate"},
                "4": {"status": "gate"},
                "5": {"status": "gate", "gate_data": {
                    "experiments": [
                        {"name": "Cold Email Test", "hypothesis": "20% response rate", "metric": "response rate", "success_criteria": "≥10%", "duration": "7 days"},
                        {"name": "Landing Page Test", "hypothesis": "5% CTR", "metric": "CTR", "success_criteria": "≥5%", "duration": "14 days"},
                    ],
                    "sprint_duration_days": 30,
                }},
            },
            "kill_conditions": [
                {"id": "kc_01", "condition": "If willingness to pay is false, this niche is dead.", "status": "signed_off"},
            ],
        }
        report = generate_final_report(session)
        
        # Check key sections are present
        assert "Startup Validation Report" in report
        assert "Digital Patch Test Logs for Beauty Therapists" in report
        assert "Paper records are unorganized" in report
        assert "Template-Based Compliance SaaS" in report
        assert "£29/mo" in report
        assert "CAC" in report
        assert "£35" in report
        assert "LTV/CAC Ratio" in report
        assert "Cold Email Test" in report
        assert "Landing Page Test" in report
        assert "ALL GATES PASSED" in report
        assert "test_session_123" in report
        assert "Next Steps" in report

    def test_incomplete_session(self):
        """Generate report even with incomplete stages."""
        session = {
            "session_id": "test_incomplete",
            "manifest": {},
            "approved_niche": "Test Niche",
            "stages": {},
            "kill_conditions": [],
        }
        report = generate_final_report(session)
        assert "Startup Validation Report" in report
        assert "Test Niche" in report

    def test_kill_condition_status(self):
        """Report shows KILL status if active kill condition."""
        session = {
            "session_id": "test_kill",
            "manifest": {},
            "approved_niche": "Test",
            "stages": {},
            "kill_conditions": [
                {"id": "kc_01", "condition": "If CAC > £100", "status": "active"},
            ],
        }
        report = generate_final_report(session)
        assert "KILL CONDITION HIT" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
