#!/usr/bin/env python3
"""Quick isolated test of rank() method with mock API."""
import os, sys, json
os.environ.setdefault("FIREWORKS_API_KEY", "test-key")
os.environ.setdefault("FIREWORKS_BASE_URL", "https://test.local")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from unittest.mock import patch
from agents import Synthesizer

# Create a synthesizer with fake history
synth = Synthesizer()
synth.history = [
    {"role": "system", "content": "You are the SYNTHESIZER..."},
    {"role": "assistant", "content": "Niche 1: ShiftPool - Hospitality Staff Rotas. Kill condition: If <60% already use scheduling software."},
    {"role": "assistant", "content": "Niche 2: ReturnRate - E-commerce Analytics. Kill condition: If Shopify Plus covers 80% of need."},
    {"role": "assistant", "content": "Niche 3: QuoteStack - Proposal Automation. Kill condition: If decision-makers view as cost not accelerator."},
]

# Test 1: Simulate model returning '>' format
print("=== Test 1: '>' separator format ===")
with patch.object(synth.client, 'chat', return_value="ShiftPool > ReturnRate > QuoteStack"):
    result = synth.rank()
    print(f"  Result: {result}")
    parsed = json.loads(result)
    assert parsed == ["ShiftPool", "ReturnRate", "QuoteStack"], f"Unexpected: {parsed}"
    print("  ✅ PASS")

# Test 2: Simulate model returning meta-commentary + '>' format
print("\n=== Test 2: Meta-commentary + '>' format ===")
with patch.object(synth.client, 'chat', return_value="The user wants me to rank.\nShiftPool > QuoteStack > ReturnRate"):
    result = synth.rank()
    print(f"  Result: {result}")
    parsed = json.loads(result)
    assert parsed == ["ShiftPool", "QuoteStack", "ReturnRate"], f"Unexpected: {parsed}"
    print("  ✅ PASS")

# Test 3: Simulate model returning quoted names with stars
print("\n=== Test 3: Quoted names with markdown ===")
with patch.object(synth.client, 'chat', return_value='"ShiftPool**" > "ReturnRate**" > "QuoteStack"'):
    result = synth.rank()
    print(f"  Result: {result}")
    parsed = json.loads(result)
    assert parsed == ["ShiftPool", "ReturnRate", "QuoteStack"], f"Unexpected: {parsed}"
    print("  ✅ PASS")

# Test 4: Simulate model returning pure garbage
print("\n=== Test 4: Pure garbage (falls through as single item) ===")
with patch.object(synth.client, 'chat', return_value="I am confused about what to do here."):
    result = synth.rank()
    print(f"  Result: {result}")
    assert "confused" in result, f"Expected raw-ish fallback: {result}"
    print("  ✅ PASS")

print("\n🎉 All rank() tests passed!")
