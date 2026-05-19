"""
Claims validator: extracts and validates the mandatory CLAIMS_BLOCK JSON
that agents append to each turn.
"""

import json
import re
from typing import Dict, List, Any


class ClaimsBlockError(Exception):
    pass


class ClaimsValidator:
    """Extracts CLAIMS_BLOCK from agent response and validates kill-condition references."""

    CLAIMS_BLOCK_RE = re.compile(
        r"CLAIMS_BLOCK[:\s]*\n*(\{.*?\})\s*(?:\Z|\n\n)",
        re.DOTALL | re.IGNORECASE
    )
    # Fallback: look for any JSON object with expected keys anywhere in text
    FALLBACK_RE = re.compile(
        r"\{[\s\S]*?(?:\"assumptions\"|\"objections_raised\"|\"objections_resolved\")[\s\S]*?\}",
        re.DOTALL
    )

    def __init__(self, session_kill_conditions: List[Dict]):
        """
        Args:
            session_kill_conditions: list of signed-off kill condition dicts,
                each with at minimum an 'id' key.
        """
        self.valid_kill_ids = {kc["id"] for kc in session_kill_conditions if "id" in kc}

    def extract(self, text: str) -> Dict[str, Any]:
        """Pull the last CLAIMS_BLOCK from the agent response. Raises on missing block."""
        matches = self.CLAIMS_BLOCK_RE.findall(text)
        if not matches:
            # Fallback: search for any JSON object with expected keys
            fallback = self.FALLBACK_RE.findall(text)
            if fallback:
                raw = fallback[-1]
            else:
                raise ClaimsBlockError("No CLAIMS_BLOCK found in agent response.")
        else:
            raw = matches[-1]

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ClaimsBlockError(f"Malformed CLAIMS_BLOCK JSON: {e}") from e

        self.validate(parsed)
        return parsed

    def validate(self, block: Dict[str, Any]) -> None:
        """Validate structure and kill-condition references. Raises ClaimsBlockError on failure."""
        # Required top-level keys
        required = {"assumptions", "objections_raised", "objections_resolved"}
        missing = required - set(block.keys())
        if missing:
            raise ClaimsBlockError(f"CLAIMS_BLOCK missing keys: {missing}")

        # Validate assumptions
        assumptions = block.get("assumptions", [])
        if not isinstance(assumptions, list):
            raise ClaimsBlockError("'assumptions' must be a list.")

        for idx, a in enumerate(assumptions):
            if not isinstance(a, dict):
                raise ClaimsBlockError(f"assumption[{idx}] must be a dict.")

            # Must have claim text
            if "claim" not in a:
                raise ClaimsBlockError(f"assumption[{idx}] missing 'claim'.")

            # Must have type
            valid_types = {"manifest", "inferred", "unverified"}
            claim_type = a.get("type", "unverified")
            if claim_type not in valid_types:
                raise ClaimsBlockError(
                    f"assumption[{idx}] 'type' must be one of {valid_types}, got '{claim_type}'"
                )

            # If kill_condition_id is present, it must be a known kill condition
            kcid = a.get("kill_condition_id")
            if kcid and kcid not in self.valid_kill_ids:
                raise ClaimsBlockError(
                    f"assumption[{idx}] references unknown kill_condition_id '{kcid}'. "
                    f"Valid IDs: {self.valid_kill_ids or 'none'}"
                )

        # Validate objections lists
        for key in ("objections_raised", "objections_resolved"):
            val = block.get(key, [])
            if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
                raise ClaimsBlockError(f"'{key}' must be a list of strings.")

    def build_error_retry_prompt(self, error_msg: str, previous_response: str) -> str:
        """Construct a prompt that asks the agent to fix the malformed CLAIMS_BLOCK."""
        return (
            f"Your previous response had an invalid CLAIMS_BLOCK: {error_msg}\n\n"
            f"Please fix the CLAIMS_BLOCK. Required format:\n"
            f"  - assumptions: list of {{claim, type, kill_condition_id?, depends_on?}}\n"
            f"  - objections_raised: list of strings\n"
            f"  - objections_resolved: list of strings\n"
            f"  - optional: proposed_niche_ids, pivot_requested\n\n"
            f"Valid kill_condition_id values: {self.valid_kill_ids or 'none'}\n"
            f"Valid types: manifest, inferred, unverified\n\n"
            f"Your corrected response (keep your full reasoning, then end with CLAIMS_BLOCK):"
        )
