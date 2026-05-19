#!/usr/bin/env python3
"""Tests for the interactive terminal gate functionality."""

import pytest
import sys
from io import StringIO
from unittest.mock import patch

import os
os.environ.setdefault("FIREWORKS_API_KEY", "test-key")
os.environ.setdefault("FIREWORKS_BASE_URL", "https://test.local")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gate_manager import GateManager


class TestPromptHumanDecision:
    def test_approve_choice(self):
        """Test [a]pprove selection."""
        gm = GateManager()
        gate_data = {
            "session_id": "test_session",
            "synthesizer_ranking": ["Niche A", "Niche B"],
            "skeptic_ranking": [],
            "convergence_type": "disputed",
            "kill_conditions": [],
            "unverified_claims": [],
        }
        
        with patch("builtins.input", side_effect=["a"]):
            decision = gm.prompt_human_decision(1, gate_data)
        
        assert decision["decision"] == "approve"
        assert "terminal prompt" in decision["rationale"].lower()
    
    def test_refine_choice(self):
        """Test [r]efine selection with rationale."""
        gm = GateManager()
        gate_data = {
            "session_id": "test_session",
            "approved_niche": "Niche A",
            "pain_points": [{"name": "Pain 1"}],
        }
        
        with patch("builtins.input", side_effect=["r", "Need more evidence on CAC"]):
            decision = gm.prompt_human_decision(2, gate_data)
        
        assert decision["decision"] == "refine"
        assert "CAC" in decision["rationale"]
    
    def test_reject_choice(self):
        """Test [x]reject selection with rationale."""
        gm = GateManager()
        gate_data = {
            "session_id": "test_session",
            "approved_niche": "Niche A",
            "approved_pain_point": "Pain 1",
            "solutions": [{"name": "Solution 1"}],
        }
        
        with patch("builtins.input", side_effect=["x", "Too competitive"]):
            decision = gm.prompt_human_decision(3, gate_data)
        
        assert decision["decision"] == "reject"
        assert "competitive" in decision["rationale"]
    
    def test_invalid_then_valid(self):
        """Test invalid input followed by valid input."""
        gm = GateManager()
        gate_data = {"session_id": "test", "synthesizer_ranking": ["A"]}
        
        with patch("builtins.input", side_effect=["invalid", "", "a"]):
            decision = gm.prompt_human_decision(1, gate_data)
        
        assert decision["decision"] == "approve"
    
    def test_keyboard_interrupt(self):
        """Test Ctrl+C handling."""
        gm = GateManager()
        gate_data = {"session_id": "test"}
        
        with patch("builtins.input", side_effect=[KeyboardInterrupt()]):
            decision = gm.prompt_human_decision(1, gate_data)
        
        assert decision["decision"] == "timeout"
        assert "interrupted" in decision["rationale"].lower()


class TestRunGateModes:
    def test_auto_approve_mode(self):
        """Test auto_approve path (test mode)."""
        gm = GateManager()
        gate_data = {
            "session_id": "test_auto",
            "synthesizer_ranking": ["Niche A"],
            "skeptic_ranking": [],
            "convergence_type": "disputed",
            "niches": {},
            "kill_conditions": [],
            "rejected_niches": [],
            "unverified_claims": [],
            "evidence_status": [],
            "momentum_summary": [],
            "transcript_summary": "Test",
        }
        
        decision = gm.run_gate(1, "test_auto", gate_data, auto_approve=True)
        
        assert decision["decision"] == "approve"
        assert "test mode" in decision["rationale"].lower()
    
    def test_non_interactive_mode(self):
        """Test non_interactive flag uses file-watching fallback when convergence is strong."""
        gm = GateManager()
        # Mock open_gate and watch_for_save to avoid actual file operations
        with patch.object(gm, "open_gate") as mock_open, \
             patch.object(gm, "watch_for_save", return_value=False) as mock_watch:
            
            gate_data = {
                "session_id": "test_ni",
                "synthesizer_ranking": ["Niche A"],
                "skeptic_ranking": ["Niche A"],
                "convergence_type": "strong",
                "niches": {},
                "kill_conditions": [],
                "rejected_niches": [],
                "unverified_claims": [],
                "evidence_status": [],
                "momentum_summary": [],
                "transcript_summary": "Test",
            }
            
            decision = gm.run_gate(1, "test_ni", gate_data, non_interactive=True)
            
            assert mock_open.called
            assert mock_watch.called
            assert decision["decision"] == "timeout"

    def test_disputed_forces_interactive(self):
        """Test that disputed convergence forces interactive mode even with non_interactive=True."""
        gm = GateManager()
        # Mock open_gate to ensure it is NOT called when disputed forces interactive
        with patch.object(gm, "open_gate") as mock_open, \
             patch("builtins.input", side_effect=["x", "Too risky"]):
            
            gate_data = {
                "session_id": "test_disputed",
                "synthesizer_ranking": ["Niche A"],
                "skeptic_ranking": ["Niche B"],
                "convergence_type": "disputed",
                "niches": {},
                "kill_conditions": [],
                "rejected_niches": [],
                "unverified_claims": [],
                "evidence_status": [],
                "momentum_summary": [],
                "transcript_summary": "Test",
            }
            
            decision = gm.run_gate(1, "test_disputed", gate_data, non_interactive=True)
            
            assert not mock_open.called, "open_gate should NOT be called when disputed forces interactive"
            assert decision["decision"] == "reject"
            assert "risky" in decision["rationale"].lower()


class TestGatePathGeneration:
    def test_gate_path(self):
        """Test gate file path generation."""
        gm = GateManager()
        path = gm._gate_path(1, "session_123")
        assert "stage1" in path
        assert "gate-stage1-session_123.md" in path
    
    def test_decision_path(self):
        """Test decision JSON path generation."""
        gm = GateManager()
        path = gm._decision_path(2, "session_456")
        assert "stage2" in path
        assert "decision.json" in path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
