"""Deterministic scoring for the coaching loop.

Kept free of LLM calls so readiness is reproducible: the same observations
always produce the same score.
"""
from typing import List

from src.langgraphagenticai.coach.state import SkillLevel

# The resume is the weakest evidence (it is self-reported), so once a candidate
# has been tested its weight drops to this share.
BASELINE_WEIGHT = 0.3
# Newer observations count more: weight of an observation from cycle c in the
# current cycle n is RECENCY ** (n - c).
RECENCY = 0.6


def skill_level(skill: SkillLevel, current_cycle: int) -> float:
    tested = [o for o in skill.observations if o.source != "resume"]
    if not tested:
        return skill.baseline
    weights = [RECENCY ** max(current_cycle - o.cycle, 0) for o in tested]
    observed = sum(w * o.value for w, o in zip(weights, tested)) / sum(weights)
    return round(BASELINE_WEIGHT * skill.baseline + (1 - BASELINE_WEIGHT) * observed, 2)


def readiness(skills: List[SkillLevel]) -> float:
    """Weighted share of required level met across skills, 0-100."""
    total = sum(s.jd_weight for s in skills)
    if not total:
        return 0.0
    met = sum(s.jd_weight * min(s.level / s.required_level, 1.0) for s in skills)
    return round(100 * met / total, 1)


def priority(skill: SkillLevel) -> float:
    """Order for learning and interview targeting: important and far behind first."""
    return skill.jd_weight * skill.gap


def interview_observation(avg_score: float, difficulty: int) -> float:
    """A good answer to an easy question cannot prove an expert level, so the
    observed level is capped one above the question's difficulty."""
    return round(min(avg_score, difficulty + 1, 5.0), 2)


def checkpoint_observation(score: float, required_level: int) -> float:
    """Checkpoint quizzes are pitched at the required level; passing them all
    demonstrates that level."""
    return round(score * required_level, 2)
