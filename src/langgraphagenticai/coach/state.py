"""State for the candidate coaching loop.

The LLM produces *observations* (skill levels, rubric scores); readiness is
computed from those observations by plain code in ``scoring.py`` so the number
the candidate sees is deterministic and explainable.
"""
from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ---------------- skill model ---------------- #

class RoleSkill(BaseModel):
    """A skill a target role needs. Comes from a role profile, or is
    extracted from a pasted JD during diagnosis."""
    skill: str
    required_level: int = Field(..., ge=1, le=5)
    jd_weight: float = Field(..., ge=0, le=1)


class Observation(BaseModel):
    source: Literal["resume", "checkpoint", "interview"]
    value: float = Field(..., ge=0, le=5, description="Observed skill level, 0-5.")
    note: str = ""
    cycle: int = 0


class SkillLevel(BaseModel):
    skill: str
    required_level: int = Field(..., ge=1, le=5, description="Level the target role needs.")
    jd_weight: float = Field(..., ge=0, le=1, description="How central the skill is to the role.")
    baseline: float = Field(0, ge=0, le=5, description="Level inferred from the resume.")
    level: float = Field(0, ge=0, le=5, description="Current estimate after all observations.")
    evidence: List[str] = Field(default_factory=list, description="Resume lines backing the baseline.")
    observations: List[Observation] = Field(default_factory=list)

    @property
    def gap(self) -> float:
        return max(self.required_level - self.level, 0.0)


# ---------------- learning plan ---------------- #

class Resource(BaseModel):
    title: str
    url: str
    type: str = "article"  # docs | course | video | github | article
    source: str = ""       # site name, e.g. "pytorch.org"
    meta: str = ""         # quality signal, e.g. "PyTorch · 14 min · 81K views", "★ 32.5K"


class Topic(BaseModel):
    title: str
    why: str = ""  # one line: what it unlocks for the role
    resources: List[Resource] = Field(default_factory=list)


class SkillTopics(BaseModel):
    """What to study for one gap skill: skill-wide sources (a full course, a
    GitHub repo) plus topics in learning order, each with its own sources."""
    skill: str
    resources: List[Resource] = Field(default_factory=list)
    topics: List[Topic] = Field(default_factory=list)


# ---------------- checkpoints ---------------- #

class QuizQuestion(BaseModel):
    question: str
    options: List[str]
    answer_index: int
    explanation: str = ""
    # Set when the question comes from a web page; empty for model-written ones.
    bank_id: str = ""
    source_name: str = ""
    source_url: str = ""


class QuizReview(QuizQuestion):
    """A graded quiz question, safe to show once the quiz is submitted."""
    chosen: int


class CheckpointResult(BaseModel):
    skill: str
    cycle: int
    score: float  # 0-1
    skipped: bool = False
    review: List[QuizReview] = Field(default_factory=list)


# ---------------- interview ---------------- #

class RubricScore(BaseModel):
    correctness: int = Field(..., ge=1, le=5)
    depth: int = Field(..., ge=1, le=5)
    communication: int = Field(..., ge=1, le=5)

    @property
    def average(self) -> float:
        return (self.correctness + self.depth + self.communication) / 3


class InterviewTurn(BaseModel):
    # "intro" (the opening "introduce yourself"), "resume" (on a project or
    # achievement from the resume) or "skill" (on one of the role's skills).
    # An intro turn's skill is "Introduction", which is not a role skill, so it
    # never moves a skill level; a resume turn counts for the skill it shows.
    kind: Literal["intro", "resume", "skill"] = "skill"
    skill: str
    difficulty: int = Field(..., ge=1, le=5)
    question: str
    is_follow_up: bool = False
    # Id of the web question the question was built on ("" if none), and what a
    # strong answer covers; the grader scores against these.
    bank_id: str = ""
    key_points: List[str] = Field(default_factory=list)
    # Page the question came from ("" if model-written); shown to the candidate.
    source_name: str = ""
    source_url: str = ""
    answer: Optional[str] = None
    voice_metrics: Dict[str, float] = Field(default_factory=dict)
    score: Optional[RubricScore] = None
    feedback: str = ""
    needs_follow_up: bool = False
    critic_note: str = ""


# ---------------- progress ---------------- #

class ReadinessSnapshot(BaseModel):
    cycle: int
    readiness: float  # 0-100
    per_skill: Dict[str, float]
    at: str


class CoachState(BaseModel):
    # --- inputs ---
    candidate_id: str
    target_role: str = ""
    resume_text: str
    # Either a role profile (role_skills) or a pasted JD drives the diagnosis.
    role_slug: Optional[str] = None
    role_skills: List[RoleSkill] = Field(default_factory=list)
    jd_text: str = ""
    target_readiness: float = 90
    # Main questions in the final interview, the intro and resume questions
    # included; follow-ups are extra.
    interview_turns: int = 8

    # --- diagnosis ---
    skills: List[SkillLevel] = Field(default_factory=list)

    # --- learning ---
    plan: List[SkillTopics] = Field(default_factory=list)
    checkpoint_queue: List[str] = Field(default_factory=list)
    current_quiz_skill: Optional[str] = None
    current_quiz: List[QuizQuestion] = Field(default_factory=list)
    quiz_answers: List[int] = Field(default_factory=list)
    checkpoints: List[CheckpointResult] = Field(default_factory=list)
    skip_checkpoints: bool = False
    # Set when the candidate asks for a different skill's assessment first.
    switch_to: Optional[str] = None

    # --- interview ---
    interview: List[InterviewTurn] = Field(default_factory=list)
    # Set when the candidate ends the interview before its last question.
    interview_ended: bool = False
    # Earlier attempts when the interview is retaken, oldest first.
    past_interviews: List[List[InterviewTurn]] = Field(default_factory=list)

    # --- output ---
    # Sessions are a single pass, so this stays 0; kept for saved sessions and
    # the cycle column of progress rows.
    cycle: int = 0
    history: List[ReadinessSnapshot] = Field(default_factory=list)
    summary: str = ""
    next_steps: List[str] = Field(default_factory=list)
    status: Literal["diagnosing", "learning", "interviewing", "ready", "finished"] = "diagnosing"
    # Set when the candidate ends the session. After the interview they can
    # keep taking and retaking assessments until then.
    closed: bool = False

    @property
    def interview_done(self) -> bool:
        return self.status in ("ready", "finished")
