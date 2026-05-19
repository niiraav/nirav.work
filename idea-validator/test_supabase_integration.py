#!/usr/bin/env python3
"""Tests for Supabase lead count integration."""

import pytest
import sys
import os

os.environ.setdefault("FIREWORKS_API_KEY", "test-key")
os.environ.setdefault("FIREWORKS_BASE_URL", "https://test.local")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch, MagicMock
import tools
from config import LEAD_BASE_SEGMENTS


class TestRefreshLeadCounts:
    def test_fallback_when_no_supabase(self):
        """If SUPABASE_URL is not set, return manifest estimates."""
        with patch.object(tools, "SUPABASE_URL", ""), patch.object(tools, "SUPABASE_KEY", ""):
            counts = tools.refresh_lead_counts()
            for segment, estimate in LEAD_BASE_SEGMENTS.items():
                assert counts[segment] == estimate, f"Expected {estimate} for {segment}, got {counts[segment]}"
    
    def test_supabase_query_success(self):
        """If Supabase is available, aggregate live counts from category rows."""
        # Mock Supabase returning rows with categories that map to "trades"
        mock_result = MagicMock()
        mock_result.data = [
            {"category": "Plumbing"},
            {"category": "Plumbing"},
            {"category": "Electrical"},
        ]
        mock_client = MagicMock()
        
        # Build the query chain: client.table("leads").select("category").not_.is_("category", "null").execute()
        mock_table = MagicMock()
        mock_select = MagicMock()
        mock_not = MagicMock()
        mock_is = MagicMock()
        
        mock_client.table.return_value = mock_table
        mock_table.select.return_value = mock_select
        mock_select.not_ = mock_not
        mock_not.is_.return_value = mock_is
        mock_is.execute.return_value = mock_result
        
        with patch.object(tools, "SUPABASE_URL", "https://test.supabase.co"), \
             patch.object(tools, "SUPABASE_KEY", "test-key"), \
             patch("supabase.create_client", return_value=mock_client):
            
            counts = tools.refresh_lead_counts(segments=["trades"])
            assert counts["trades"] == 3  # 3 rows mapped to trades
            # Only requested segment is refreshed
            assert "trades" in tools.get_all_lead_counts()
    
    def test_supabase_error_falls_back(self):
        """If Supabase query raises, return estimate."""
        mock_client = MagicMock()
        mock_client.table.return_value.select.return_value.not_.return_value.is_.return_value.execute.side_effect = Exception("Connection refused")
        
        with patch.object(tools, "SUPABASE_URL", "https://test.supabase.co"), \
             patch.object(tools, "SUPABASE_KEY", "test-key"), \
             patch("supabase.create_client", return_value=mock_client):
            
            counts = tools.refresh_lead_counts(segments=["beauty_health"])
            assert counts["beauty_health"] == LEAD_BASE_SEGMENTS["beauty_health"]


class TestGetLeadCount:
    def test_cache_hit(self):
        """If live count is cached, return it without querying."""
        tools._LIVE_COUNTS["beauty_health"] = 99999
        with patch.object(tools, "SUPABASE_URL", ""), patch.object(tools, "SUPABASE_KEY", ""):
            count = tools.get_lead_count("beauty_health", use_cache=True)
            assert count == 99999
        # Clean up
        del tools._LIVE_COUNTS["beauty_health"]
    
    def test_cache_miss_falls_back(self):
        """If no cache and no Supabase, return estimate."""
        tools._LIVE_COUNTS.clear()
        with patch.object(tools, "SUPABASE_URL", ""), patch.object(tools, "SUPABASE_KEY", ""):
            count = tools.get_lead_count("automotive", use_cache=True)
            assert count == LEAD_BASE_SEGMENTS["automotive"]
    
    def test_segment_normalization(self):
        """Segment names with spaces should normalize to underscores."""
        tools._LIVE_COUNTS.clear()
        with patch.object(tools, "SUPABASE_URL", ""), patch.object(tools, "SUPABASE_KEY", ""):
            count = tools.get_lead_count("food hospitality", use_cache=True)
            assert count == LEAD_BASE_SEGMENTS["food_hospitality"]


class TestFormatLeadCounts:
    def test_total_included(self):
        """Total addressable leads should be included in output."""
        tools._LIVE_COUNTS.clear()
        formatted = tools.format_lead_counts()
        assert "Total addressable leads" in formatted
        total = sum(LEAD_BASE_SEGMENTS.values())
        assert f"~{total:,}" in formatted
    
    def test_refreshed_counts_override(self):
        """Refreshed counts should override cached counts."""
        refreshed = {"beauty_health": 99999, "automotive": 1000}
        formatted = tools.format_lead_counts(refreshed_counts=refreshed)
        assert "Beauty Health" in formatted
        assert "~99,999" in formatted or "~99999" in formatted


class TestInjectLeadCountsIntoManifest:
    def test_injects_refreshed_counts(self):
        """Manifest should be updated with refreshed counts."""
        manifest = {
            "lead_segments": {
                "beauty_health": 7800,
                "automotive": 8200,
            }
        }
        tools._LIVE_COUNTS.clear()
        
        with patch.object(tools, "SUPABASE_URL", ""), patch.object(tools, "SUPABASE_KEY", ""):
            updated = tools.inject_lead_counts_into_manifest(manifest)
            # With no Supabase, should use estimates
            assert updated["lead_segments"]["beauty_health"] == 7800
            assert "_original_lead_segments" in updated
            assert updated["_original_lead_segments"]["beauty_health"] == 7800


class TestStage1LeadCountInjection:
    def test_synthesizer_prompt_includes_counts(self):
        """Synthesizer initialization should include lead counts in prompt."""
        from agents import Synthesizer
        
        tools._LIVE_COUNTS.clear()
        tools._LIVE_COUNTS["beauty_health"] = 99999
        
        synth = Synthesizer()
        manifest = {
            "lead_segments": {"beauty_health": 7800},
            "technical_constraints": ["No mobile app"],
            "budget_ceiling": {"monthly_burn": 5000, "max_cac": 50},
            "timeline_months": 6,
        }
        context = {
            "manifest": manifest,
            "rejected_niches": [],
            "required_evidence": [],
            "lead_counts": {"beauty_health": 99999, "automotive": 1000},
        }
        
        synth.initialize(stage_num=1, context=context)
        
        # Check that the user message includes the live counts
        user_msg = synth.history[1]["content"]
        assert "99,999" in user_msg, f"Live lead count not in prompt: {user_msg[:500]}"
        assert "Total addressable leads" in user_msg
    
    def test_synthesizer_prompt_falls_back_to_manifest(self):
        """If no lead_counts in context, use manifest segments."""
        from agents import Synthesizer
        
        synth = Synthesizer()
        manifest = {
            "lead_segments": {"beauty_health": 7800},
            "technical_constraints": [],
            "budget_ceiling": {"monthly_burn": 5000, "max_cac": 50},
            "timeline_months": 6,
        }
        context = {
            "manifest": manifest,
            "rejected_niches": [],
            "required_evidence": [],
        }
        
        synth.initialize(stage_num=1, context=context)
        
        user_msg = synth.history[1]["content"]
        assert "7,800" in user_msg, f"Manifest lead count not in prompt: {user_msg[:500]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
