#!/usr/bin/env python3
"""Unit tests for llm_extract_* wrappers.

Mocks the KimiClient.chat() method to test:
1. LLM returns valid JSON → parsed correctly
2. LLM returns invalid/malformed → falls back to regex
3. Edge cases: empty input, no matches
"""

import sys
import json
from unittest.mock import patch, MagicMock

sys.path.insert(0, "/Users/niravarvinda/Workspace/projects/nirav-work/idea-validator")

from agents import (
    llm_extract_pricing_tiers,
    llm_extract_unit_economics,
    llm_extract_sprint_plan,
    llm_extract_niche_names,
    llm_extract_kill_conditions,
    extract_pricing_tiers,  # regex fallback
    extract_unit_economics,   # regex fallback
    extract_sprint_plan,      # regex fallback
    extract_niche_names,      # regex fallback
    extract_kill_conditions,  # regex fallback
)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_mock_openai(return_value: str):
    """Create a mock OpenAI client whose chat.completions.create returns the value."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_message = MagicMock()
    mock_message.content = return_value
    mock_choice.message = mock_message
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client


# ---------------------------------------------------------------------------
# Tests: pricing tiers
# ---------------------------------------------------------------------------

def test_llm_extract_pricing_tiers_valid_json():
    """LLM returns valid JSON array — should parse correctly."""
    mock_json = json.dumps([
        {"name": "Solo", "price_str": "£29", "period": "month", "description": "For solo traders"},
        {"name": "Team", "price_str": "£99", "period": "month", "description": "For teams"},
    ])
    
    with patch("agents.OpenAI", return_value=_make_mock_openai(mock_json)):
        result = llm_extract_pricing_tiers("Some pricing text")
    
    assert len(result) == 2
    assert result[0]["name"] == "Solo"
    assert result[0]["price_str"] == "£29"
    assert result[1]["period"] == "month"
    print("✅ test_llm_extract_pricing_tiers_valid_json")


def test_llm_extract_pricing_tiers_invalid_json_fallback():
    """LLM returns garbage — should fall back to regex extractor."""
    sample_text = """
    **Solo Plan — £29/mo**: For individual users
    **Team Plan — £99/mo**: For teams up to 10
    """
    
    with patch("agents.OpenAI", return_value=_make_mock_openai("not json")):
        result = llm_extract_pricing_tiers(sample_text)
    
    # Should fallback to regex and find both tiers
    assert len(result) >= 1
    print(f"✅ test_llm_extract_pricing_tiers_invalid_json_fallback (found {len(result)} tiers)")


def test_llm_extract_pricing_tiers_empty_input():
    """Empty input should return empty list (no crash)."""
    with patch("agents.OpenAI", return_value=_make_mock_openai("[]")):
        result = llm_extract_pricing_tiers("")
    
    assert result == []
    print("✅ test_llm_extract_pricing_tiers_empty_input")


# ---------------------------------------------------------------------------
# Tests: unit economics
# ---------------------------------------------------------------------------

def test_llm_extract_unit_economics_valid_json():
    """LLM returns valid JSON object — should parse with numeric coercion."""
    mock_json = json.dumps({
        "cac": 45,
        "ltv": 500,
        "gross_margin": 0.82,
        "payback_months": 1.2,
    })
    
    with patch("agents.OpenAI", return_value=_make_mock_openai(mock_json)):
        result = llm_extract_unit_economics("Some unit economics text")
    
    assert result["cac"] == 45.0
    assert result["ltv"] == 500.0
    assert result["gross_margin"] == 0.82
    assert result["payback_months"] == 1.2
    print("✅ test_llm_extract_unit_economics_valid_json")


def test_llm_extract_unit_economics_null_values():
    """LLM returns null for some fields — should handle gracefully."""
    mock_json = json.dumps({
        "cac": 45,
        "ltv": None,
        "gross_margin": None,
        "payback_months": None,
    })
    
    with patch("agents.OpenAI", return_value=_make_mock_openai(mock_json)):
        result = llm_extract_unit_economics("Some text")
    
    assert result["cac"] == 45.0
    assert result["ltv"] is None
    print("✅ test_llm_extract_unit_economics_null_values")


def test_llm_extract_unit_economics_fallback():
    """LLM returns invalid JSON — should fallback to regex."""
    sample_text = """
    CAC: £35
    LTV: £420
    Gross margin: 82%
    Payback: 1.3 months
    """
    
    with patch("agents.OpenAI", return_value=_make_mock_openai("garbage")):
        result = llm_extract_unit_economics(sample_text)
    
    assert result["cac"] == 35.0
    assert result["ltv"] == 420.0
    print("✅ test_llm_extract_unit_economics_fallback")


# ---------------------------------------------------------------------------
# Tests: sprint plan
# ---------------------------------------------------------------------------

def test_llm_extract_sprint_plan_valid_json():
    """LLM returns valid JSON array of experiments."""
    mock_json = json.dumps([
        {
            "name": "Landing Page Test",
            "hypothesis": "Tradespeople will sign up",
            "metric": "Conversion rate",
            "success_criteria": ">5%",
            "duration": "7 days",
        }
    ])
    
    with patch("agents.OpenAI", return_value=_make_mock_openai(mock_json)):
        result = llm_extract_sprint_plan("Some sprint text")
    
    assert len(result) == 1
    assert result[0]["name"] == "Landing Page Test"
    assert result[0]["duration"] == "7 days"
    print("✅ test_llm_extract_sprint_plan_valid_json")


def test_llm_extract_sprint_plan_fallback():
    """LLM returns invalid JSON — should fallback to regex."""
    sample_text = """
    **Experiment 1: Landing Page Test**
    - Hypothesis: Tradespeople will sign up for a waitlist
    - Metric: Email capture rate
    - Success: >10% conversion
    - Duration: 7 days
    """
    
    with patch("agents.OpenAI", return_value=_make_mock_openai("not valid")):
        result = llm_extract_sprint_plan(sample_text)
    
    assert len(result) >= 1
    print(f"✅ test_llm_extract_sprint_plan_fallback (found {len(result)} experiments)")


# ---------------------------------------------------------------------------
# Tests: niche names
# ---------------------------------------------------------------------------

def test_llm_extract_niche_names_valid_json():
    """LLM returns valid JSON array of strings."""
    mock_json = json.dumps(["Niche A", "Niche B", "Niche C"])
    
    with patch("agents.OpenAI", return_value=_make_mock_openai(mock_json)):
        result = llm_extract_niche_names("Some niche text")
    
    assert result == ["Niche A", "Niche B", "Niche C"]
    print("✅ test_llm_extract_niche_names_valid_json")


def test_llm_extract_niche_names_fallback():
    """LLM returns invalid JSON — should fallback to regex."""
    sample_text = 'Niche 1: "SaaS for Dentists"\nNiche 2: "Fleet Management Software"'
    
    with patch("agents.OpenAI", return_value=_make_mock_openai("bad")):
        result = llm_extract_niche_names(sample_text)
    
    assert len(result) >= 1
    print(f"✅ test_llm_extract_niche_names_fallback (found {len(result)} names)")


# ---------------------------------------------------------------------------
# Tests: kill conditions
# ---------------------------------------------------------------------------

def test_llm_extract_kill_conditions_valid_json():
    """LLM returns valid JSON array of strings."""
    mock_json = json.dumps([
        "If CAC exceeds £100, this niche is dead",
        "If LTV/CAC is below 3x, abandon immediately",
    ])
    
    with patch("agents.OpenAI", return_value=_make_mock_openai(mock_json)):
        result = llm_extract_kill_conditions("Some kill conditions text")
    
    assert len(result) == 2
    assert result[0]["condition"] == "If CAC exceeds £100, this niche is dead"
    assert result[0]["status"] == "proposed"
    assert result[0]["id"] == "kc_01"
    print("✅ test_llm_extract_kill_conditions_valid_json")


def test_llm_extract_kill_conditions_fallback():
    """LLM returns invalid JSON — should fallback to regex."""
    sample_text = """
    Kill Condition 1: If market size is under 1000 leads, this niche is dead.
    Kill Condition 2: If CAC exceeds £50 for 3 months, this niche is dead.
    """
    
    with patch("agents.OpenAI", return_value=_make_mock_openai("nope")):
        result = llm_extract_kill_conditions(sample_text)
    
    assert len(result) >= 1
    print(f"✅ test_llm_extract_kill_conditions_fallback (found {len(result)} conditions)")


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*60)
    print("  LLM Extract Wrapper Tests")
    print("="*60 + "\n")
    
    test_llm_extract_pricing_tiers_valid_json()
    test_llm_extract_pricing_tiers_invalid_json_fallback()
    test_llm_extract_pricing_tiers_empty_input()
    
    test_llm_extract_unit_economics_valid_json()
    test_llm_extract_unit_economics_null_values()
    test_llm_extract_unit_economics_fallback()
    
    test_llm_extract_sprint_plan_valid_json()
    test_llm_extract_sprint_plan_fallback()
    
    test_llm_extract_niche_names_valid_json()
    test_llm_extract_niche_names_fallback()
    
    test_llm_extract_kill_conditions_valid_json()
    test_llm_extract_kill_conditions_fallback()
    
    print("\n" + "="*60)
    print("  ✅ All 11 tests passed")
    print("="*60)
