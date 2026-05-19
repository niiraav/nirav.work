"""
Configuration and environment setup for the falsification engine.
Uses the local Fireworks proxy at localhost:9999 for resilient deliberation.
"""

import os
import json

# --- API Configuration ---
# Route through the local proxy for key rotation and resilience
# NOTE: Proxy is unstable under load; falling back to direct API for testing
FIREWORKS_API_KEY = os.getenv("FIREWORKS_API_KEY", "")
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"

# Kimi model on Fireworks
KIMI_MODEL = os.getenv("KIMI_MODEL", "accounts/fireworks/models/kimi-k2p6")

# --- Supabase ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

# --- Paths ---
SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")
GATES_DIR = os.path.join(os.path.dirname(__file__), "gates")

OBSIDIAN_VAULT_PATH = os.path.expanduser(
    "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/wiki/startup-decisions"
)

# --- Session Defaults ---
DEFAULT_MAX_PIVOTS = 1
DEFAULT_MAX_TURNS = 5
DEFAULT_TOKEN_CEILING = 80000

# --- Manifest ---
MANIFEST_SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "manifest_schema.json")

# --- Search Platforms (domain, label) ---
SEARCH_PLATFORMS = [
    ("reddit.com", "Reddit Discussions"),
    ("quora.com", "Quora Questions"),
    ("g2.com", "G2 Reviews"),
    ("trustpilot.com", "Trustpilot Reviews"),
    ("linkedin.com", "LinkedIn Posts"),
]

# --- Lead Base Segments (fallback estimates when Supabase is unavailable) ---
LEAD_BASE_SEGMENTS = {
    "automotive": 8200,
    "food_hospitality": 12800,
    "beauty_health": 7800,
    "professional_services": 5300,
    "ecom": 7514,
    "trades": 3400,
}


def load_manifest(path: str = None) -> dict:
    """Load and return the session manifest. Falls back to manifest_example.json."""
    if path is None:
        path = os.path.join(os.path.dirname(__file__), "manifest.json")
    if not os.path.exists(path):
        # Try example manifest
        example = os.path.join(os.path.dirname(__file__), "manifest_example.json")
        if os.path.exists(example):
            path = example
        else:
            raise FileNotFoundError(f"No manifest found at {path} or manifest_example.json")
    with open(path) as f:
        return json.load(f)


def check_manifest_evidence(manifest: dict) -> list:
    """Return list of blocking evidence items that are still pending."""
    blocking = []
    for item in manifest.get("required_evidence", []):
        if item.get("blocking", False) and item.get("status", "pending") == "pending":
            blocking.append(item)
    return blocking


def get_session_constraints(manifest: dict) -> dict:
    """Extract session constraints from manifest with defaults."""
    sc = manifest.get("session_constraints", {})
    return {
        "max_pivots": sc.get("max_pivots", DEFAULT_MAX_PIVOTS),
        "max_turns": sc.get("max_turns_per_stage", DEFAULT_MAX_TURNS),
        "token_ceiling": sc.get("token_ceiling", DEFAULT_TOKEN_CEILING),
    }
