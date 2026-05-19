"""
Momentum tracker: monitors convergence health per round.
Formula: (resolved - raised) / (resolved + raised)
"""

from typing import List, Dict, Optional


class MomentumTracker:
    """Tracks objections raised vs resolved per turn to detect deadlock or deterioration.
    
    Core insight: an objection is "resolved" if it was raised in a previous round
    but does NOT appear in the current round's Skeptic response. The Synthesizer's
    defense successfully addressed it.
    """

    def __init__(self):
        self.rounds: List[Dict] = []
        self._prev_objections: List[str] = []  # Track objections from previous round

    def record_turn(self, objections_raised: List[str], objections_resolved: List[str] = None) -> Optional[float]:
        """Record a turn and return convergence health score.
        
        If objections_resolved is not provided, computes it by comparing
        objections_raised against _prev_objections from the previous round.
        An objection is "resolved" if it was in _prev_objections but its
        core topic (first 4 words) does NOT appear in any current objection.
        """
        if objections_resolved is None:
            objections_resolved = self._compute_resolved(objections_raised)
        
        raised = len(objections_raised)
        resolved = len(objections_resolved)

        if raised + resolved == 0:
            health = None  # Ranking turn — no objections
        else:
            health = (resolved - raised) / (resolved + raised)

        self.rounds.append({
            "turn": len(self.rounds) + 1,
            "raised": raised,
            "resolved": resolved,
            "health": health,
        })
        
        # Store current objections for next round's resolution comparison
        self._prev_objections = list(objections_raised)
        return health

    def _compute_resolved(self, current_objections: List[str]) -> List[str]:
        """Compare current objections against previous round's objections.
        
        An objection is "resolved" if it was in _prev_objections but its
        core topic words don't appear in any current objection.
        """
        if not self._prev_objections:
            return []
        
        resolved = []
        current_text = " ".join(current_objections).lower()
        
        for prev_obj in self._prev_objections:
            # Extract core topic words (first 4 significant words)
            topic_words = [w for w in prev_obj.lower().split() 
                          if len(w) > 3 and w not in {"this", "that", "with", "from", "have", "been", "were", "they", "their", "there", "would", "should", "could"}][:4]
            
            if not topic_words:
                continue
            
            # Check if ANY of the topic words appear in current objections
            topic_present = any(word in current_text for word in topic_words)
            
            if not topic_present:
                # Previous objection's topic is gone — it's resolved
                resolved.append(prev_obj)
        
        return resolved

    def is_deadlocked(self, lookback: int = 2) -> bool:
        """Check if health has been flat (between -0.2 and +0.2) for `lookback` consecutive rounds."""
        if len(self.rounds) < lookback:
            return False
        recent = self.rounds[-lookback:]
        return all(
            r["health"] is not None and -0.2 <= r["health"] <= 0.2
            for r in recent
        )

    def is_deteriorating(self, lookback: int = 2) -> bool:
        """Check if health is negative for `lookback` consecutive rounds."""
        if len(self.rounds) < lookback:
            return False
        recent = self.rounds[-lookback:]
        return all(
            r["health"] is not None and r["health"] < -0.2
            for r in recent
        )

    def is_converging(self) -> bool:
        """Last round had positive health (more resolved than raised)."""
        if not self.rounds:
            return False
        health = self.rounds[-1]["health"]
        return health is not None and health > 0.2

    def latest_health(self) -> Optional[float]:
        """Return the health score of the most recent round, or None."""
        if not self.rounds:
            return None
        return self.rounds[-1]["health"]

    def summary(self) -> List[Dict]:
        """Return all rounds for gate output."""
        return self.rounds

    def reset(self):
        """Clear tracking for a new deliberation."""
        self.rounds = []
        self._prev_objections = []
