#!/usr/bin/env python3
"""Tests for Stage 2 extraction functions."""

import pytest
from orchestrator import extract_pain_points_from_transcript, _collect_unverified_claims


# ---------------------------------------------------------------------------
# extract_pain_points_from_transcript
# ---------------------------------------------------------------------------

class TestExtractPainPoints:
    def test_rank_format(self):
        """**Rank N: Title** format."""
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": """
**Rank 1: Paper records create liability**
Evidence: Vagaro article says digital is more secure.

**Rank 2: Admin overhead wastes billable hours**
Evidence: MioSalon says manual messaging is tedious.

**Rank 3: Lost client history hurts retention**
Evidence: MioSalon says track previous visits.
"""
        }]
        result = extract_pain_points_from_transcript(transcript, niche_name="Digital Patch Test")
        assert len(result) == 3
        assert result[0]["name"] == "Paper records create liability"
        assert result[1]["name"] == "Admin overhead wastes billable hours"
        assert result[2]["name"] == "Lost client history hurts retention"

    def test_numbered_bold_format(self):
        """1. **Title** format."""
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": """
1. **Paper-based patch test records are hard to manage**
Evidence: Vagaro article.
2. **Time-consuming manual record keeping**
Evidence: MioSalon article.
3. **Complaint management when records are incomplete**
Evidence: Konnect article.
"""
        }]
        result = extract_pain_points_from_transcript(transcript, niche_name="Digital Patch Test")
        assert len(result) == 3
        assert "Paper-based patch test records" in result[0]["name"]
        assert "Time-consuming manual record" in result[1]["name"]

    def test_skip_competitor_headers(self):
        """Headers like **COMPETITOR REVIEWS:** must be skipped."""
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": """
**COMPETITOR REVIEWS:**
Some analysis here.

**COMPETITOR LANDSCAPE:**
More analysis.

1. **Paper-based patch test records are hard to manage**
Evidence: Vagaro.
"""
        }]
        result = extract_pain_points_from_transcript(transcript, niche_name="Digital Patch Test")
        for pp in result:
            assert "COMPETITOR" not in pp["name"]
            assert "LANDSCAPE" not in pp["name"]
            assert "REVIEWS" not in pp["name"]

    def test_skip_niche_name(self):
        """Pain points should not be the niche name itself."""
        niche = "Digital Patch Test & Treatment Logs"
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": f"""
**Rank 1: {niche}**
This is just the niche name repeated.

**Rank 2: Paper records are insecure**
Actual pain point.
"""
        }]
        result = extract_pain_points_from_transcript(transcript, niche_name=niche)
        assert len(result) == 1
        assert "Paper records" in result[0]["name"]

    def test_empty_transcript(self):
        """Empty transcript returns empty list."""
        result = extract_pain_points_from_transcript([], niche_name="Test")
        assert result == []

    def test_non_matching_stage(self):
        """Only Stage 2 entries should be processed."""
        transcript = [{
            "role": "Synthesizer", "stage": 1, "round": 1,
            "content": "**Rank 1: Some niche**"
        }]
        result = extract_pain_points_from_transcript(transcript, niche_name="Test")
        assert result == []


# ---------------------------------------------------------------------------
# _collect_unverified_claims
# ---------------------------------------------------------------------------

class TestCollectUnverifiedClaims:
    def test_basic_extraction(self):
        """Find [unverified] tagged claims."""
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": "The market is large [unverified]. Revenue is £10k MRR [unverified]."
        }]
        result = _collect_unverified_claims(transcript, stage_filter=2)
        assert len(result) == 2
        assert "market is large" in result[0]["claim"]
        assert "Revenue is £10k MRR" in result[1]["claim"]

    def test_skip_instruction_echoes(self):
        """Skip claims that are instruction echoes."""
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": "Tag unverified claims with [unverified]. I should derive pain points [unverified]."
        }]
        result = _collect_unverified_claims(transcript, stage_filter=2)
        assert len(result) == 0

    def test_skip_meta_reasoning(self):
        """Skip claims with heavy first-person reasoning."""
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": "I think I can infer that the market is big [unverified]. I believe I should check this again."
        }]
        result = _collect_unverified_claims(transcript, stage_filter=2)
        assert len(result) == 0

    def test_stage_filter(self):
        """Only collect from specified stage."""
        transcript = [
            {"role": "Synthesizer", "stage": 1, "round": 1, "content": "Stage 1 claim [unverified]."},
            {"role": "Synthesizer", "stage": 2, "round": 1, "content": "Stage 2 claim [unverified]."},
        ]
        result = _collect_unverified_claims(transcript, stage_filter=2)
        assert len(result) == 1
        assert "Stage 2 claim" in result[0]["claim"]

    def test_short_claims_skipped(self):
        """Very short claims are skipped."""
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": "Short one [unverified]."
        }]
        result = _collect_unverified_claims(transcript, stage_filter=2)
        assert len(result) == 0

    def test_max_five_claims(self):
        """Maximum 5 claims returned."""
        claims_text = " ".join([f"Claim number {i} is important [unverified]." for i in range(10)])
        transcript = [{
            "role": "Synthesizer", "stage": 2, "round": 1,
            "content": claims_text
        }]
        result = _collect_unverified_claims(transcript, stage_filter=2)
        assert len(result) == 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
