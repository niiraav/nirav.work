import os

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")

CLAUDE_MODEL = "claude-sonnet-4-6"

# Check Moonshot API docs or OpenCode config for the exact Kimi K2.6 model ID
KIMI_MODEL = os.getenv("KIMI_MODEL", "kimi-k2-0528")
MOONSHOT_BASE_URL = "https://api.moonshot.cn/v1"

MAX_ROUNDS_PER_STAGE = 3
CONFIDENCE_THRESHOLD = 70  # advance stage when confidence >= this

OBSIDIAN_PATH = os.getenv(
    "OBSIDIAN_PATH",
    os.path.expanduser(
        "~/Library/Mobile Documents/iCloud~md~obsidian/Documents/wiki/projects/startup-idea-lab"
    ),
)

SESSIONS_DIR = os.path.join(os.path.dirname(__file__), "sessions")

# Estimated lead counts per segment — used as fallback when Supabase is unavailable
LEAD_BASE_SEGMENTS = {
    "automotive": 8200,
    "food_hospitality": 12800,
    "beauty_health": 7800,
    "professional_services": 5300,
    "ecom": 7514,
    "trades": 3400,
}

SEARCH_PLATFORMS = [
    ("reddit.com", "Reddit"),
    ("quora.com", "Quora"),
    ("g2.com", "G2"),
    ("trustpilot.com", "Trustpilot"),
    ("linkedin.com", "LinkedIn"),
]
