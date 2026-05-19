#!/usr/bin/env python3
"""
Unit tests for the falsification engine deliberation loop.
Uses mock API client to avoid real API calls.
"""

import json
import sys
import os

# Set dummy env vars before imports
os.environ.setdefault("FIREWORKS_API_KEY", "test-key")
os.environ.setdefault("FIREWORKS_BASE_URL", "https://test.local")

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import Mock, patch
from agents import Synthesizer, Skeptic, extract_niche_names, extract_kill_conditions
from orchestrator import run_stage1, create_session, _filter_kill_conditions


def test_extract_niche_names():
    text = """
Niche 1: "Auto MOT Alert"
Niche 2: "Quarterly Tax Bot"
Niche 3: "GreenThumb Pro"
"""
    names = extract_niche_names(text)
    assert len(names) == 3, f"Expected 3 names, got {len(names)}"
    assert "Auto MOT Alert" in names
    print("✅ test_extract_niche_names passed")


def test_extract_kill_conditions():
    text = """
**Kill condition 1**: If fewer than 10% of UK car owners forget MOT dates, this niche is dead.
**Kill condition 2**: If CAC exceeds £50 per customer, abandon.
"""
    kc = extract_kill_conditions(text)
    assert len(kc) == 2, f"Expected 2 KC, got {len(kc)}"
    assert "10%" in kc[0]["condition"]
    print("✅ test_extract_kill_conditions passed")


def test_synthesizer_history_persistence():
    synth = Synthesizer()
    
    # Mock the API client
    mock_response = Mock()
    mock_response.choices = [Mock(message=Mock(content="Proposed: Niche A, B, C"))]
    
    with patch.object(synth.client, 'chat', return_value="Proposed: Niche A, B, C"):
        synth.initialize(stage_num=1, context={
            "manifest": {
                "lead_segments": {"test": "value"},
                "budget_ceiling": {"monthly_burn": 1000, "max_cac": 50},
                "technical_constraints": [],
            },
            "rejected_niches": [],
            "required_evidence": [],
        })
        
        assert len(synth.history) == 2  # system + user
        
        result = synth.respond()
        assert result == "Proposed: Niche A, B, C"
        assert len(synth.history) == 3  # + assistant
        
        # Test serialize/restore
        saved = synth.serialize()
        assert len(saved) == 3
        
        synth2 = Synthesizer()
        synth2.restore(saved)
        assert len(synth2.history) == 3
        assert synth2.history[0]["role"] == "system"
        print("✅ test_synthesizer_history_persistence passed")


def test_orchestrator_stage1_mock():
    """Test the full Stage 1 flow with mocked API responses."""
    manifest = {
        "lead_segments": {"test": "test"},
        "budget_ceiling": {"monthly_burn": 1000, "max_cac": 50},
        "technical_constraints": [],
        "timeline_months": 6,
        "required_evidence": [],
        "ruled_out_niches": [],
    }
    
    session = create_session(manifest, niche_hint="Test")
    
    synth = Synthesizer()
    skeptic = Skeptic()
    
    # Mock responses for the deliberation
    round_counter = [0]
    def synth_mock(messages, max_tokens=4000):
        round_counter[0] += 1
        if round_counter[0] == 1:
            return (
                "Niche 1: MOT Reminder - 'Auto MOT Alert'\n"
                "**Kill condition 1**: If fewer than 10% of UK car owners forget MOT dates, this niche is dead.\n\n"
                "Revenue model: £10k/mo at 5% conversion."
            )
        return "Defending niche. Revenue: £10k/mo."
    
    def sk_mock(messages, max_tokens=4000):
        return "NICHE 1: Auto MOT Alert — WEAK. **Verdict**: Too many incumbents. **Demand**: Prove CAC < £30."
    
    with patch.object(synth.client, 'chat', side_effect=synth_mock):
        with patch.object(skeptic.client, 'chat', side_effect=sk_mock):
            result = run_stage1(session, synth, skeptic)
    
    assert result["status"] == "gate"
    assert result["stage"] == 1
    assert "transcript" in result
    assert len(result["transcript"]) >= 2  # At least Synthesizer + Skeptic R1
    
    # Check kill conditions were extracted
    assert len(session.get("kill_conditions", [])) > 0
    
    # Check agent histories were saved
    assert "agent_histories" in session
    assert "synthesizer" in session["agent_histories"]
    assert "skeptic" in session["agent_histories"]
    
    print("✅ test_orchestrator_stage1_mock passed")


def test_filter_kill_conditions():
    """Test that kill conditions are filtered when niche changes."""
    kc = [
        {"id": "kc_01", "condition": "If HMRC MTD VAT API does not support marketplace data", "status": "signed_off"},
        {"id": "kc_02", "condition": "If the DVSA API remains unavailable AND garages require MOT integration", "status": "signed_off"},
        {"id": "kc_03", "condition": "If CAC exceeds £50 per customer", "status": "signed_off"},
    ]
    
    # Ecom niche — kc_02 about DVSA/MOT garages should become inactive
    filtered = _filter_kill_conditions(kc, "Ecom VAT Filing")
    assert len(filtered) == 3
    assert filtered[0]["status"] == "signed_off"  # HMRC is relevant to tax/ecom
    assert filtered[1]["status"] == "inactive"    # DVSA/garage is NOT relevant to ecom
    assert "automotive" in filtered[1].get("reason", "").lower()
    assert filtered[2]["status"] == "signed_off"  # CAC is universal
    
    # Automotive niche — kc_02 should stay active
    filtered_auto = _filter_kill_conditions(kc, "Automotive MOT Tool")
    assert filtered_auto[1]["status"] == "signed_off"  # DVSA is relevant to automotive
    
    print("✅ test_filter_kill_conditions passed")


if __name__ == "__main__":
    test_extract_niche_names()
    test_extract_kill_conditions()
    test_synthesizer_history_persistence()
    test_orchestrator_stage1_mock()
    print("\n🎉 All tests passed!")
