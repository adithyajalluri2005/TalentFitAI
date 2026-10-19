"""Sourced interview and assessment questions, and how they are picked.

Every question here comes from a web page (see web_questions.py) and links to
it, so the candidate can see where a question and its answer come from. This
module holds the question types and the plain-code selection used by the
interviewer (seeds near a difficulty) and the assessments (a quiz spread over
the studied topics).
"""
import hashlib
import random
import re
from typing import Iterable, List, Set, Tuple

from pydantic import BaseModel, Field, field_validator


class _Sourced(BaseModel):
    id: str
    skill: str = Field(..., min_length=1)
    difficulty: int = Field(..., ge=1, le=5)
    question: str = Field(..., min_length=5)
    source_name: str = Field(..., min_length=1)
    source_url: str

    @field_validator("source_url")
    @classmethod
    def _url(cls, v: str) -> str:
        if not re.match(r"^https?://[^\s/]+\.[^\s]+$", v):
            raise ValueError("must be a full http(s) URL")
        return v


class SourcedQuestion(_Sourced):
    """A spoken interview question with what a strong answer covers."""
    key_points: List[str] = Field(..., min_length=2, max_length=6)


class SourcedMCQ(_Sourced):
    """A multiple-choice assessment question."""
    topic: str = ""
    options: List[str] = Field(..., min_length=4, max_length=4)
    answer_index: int = Field(..., ge=0, le=3)
    explanation: str = ""

    @field_validator("options")
    @classmethod
    def _options(cls, v: List[str]) -> List[str]:
        if any(not o for o in v):
            raise ValueError("all four options are required")
        if len({o.lower() for o in v}) < 4:
            raise ValueError("options must be different")
        return v

    def shuffled(self, seed: str) -> Tuple[List[str], int]:
        """Options in a stable random order, so the answer is not always the
        position the page listed it in. Left as-is when an option refers to the
        others by position or as a group ("All of the above", "Both A and B")."""
        if any(_POSITIONAL.search(o) for o in self.options):
            return list(self.options), self.answer_index
        order = list(range(4))
        random.Random(f"{self.id}|{seed}").shuffle(order)
        return [self.options[i] for i in order], order.index(self.answer_index)


_POSITIONAL = re.compile(
    r"\b(all|none|both|neither)\b.*\b(above|options|of these)\b"  # "All of the above", "Both of these"
    r"|^\s*(both|only)\s+[a-d]\b"                                 # "Both A and C", "Only B"
    r"|^\s*[a-d]\s+(and|&|or)\s+[a-d]\s*$",                       # "A and B" as the whole option
    re.IGNORECASE,
)


def _tokens(name: str) -> Set[str]:
    return set(re.findall(r"[a-z0-9+#]+", name.lower())) - {"and", "or", "the"}


def skill_matches(name: str, skill: str) -> bool:
    """True when ``skill`` names the same thing as ``name``, allowing a
    qualifier: "SQL (PostgreSQL)" and "Python 3" match "SQL" and "Python",
    but "Scripting (Bash/Python)" does not match "Python"."""
    have, wanted = _tokens(name), _tokens(skill)
    if not have or not wanted:
        return False
    if have == wanted:
        return True
    small, big = sorted((have, wanted), key=len)
    return small <= big and len(big) - len(small) <= 1


def skill_key(skill: str) -> str:
    """Normalised skill name used in ids: "SQL (PostgreSQL)" -> "sql_postgresql"."""
    return "_".join(re.findall(r"[a-z0-9+#]+", skill.lower())).replace("+", "p").replace("#", "s")[:40]


def question_id(prefix: str, skill: str, question: str) -> str:
    """``<prefix>-<skill key>-<hash>``, e.g. "web-iq-sql-1a2b3c4d5e". Stable, so
    "already asked" survives a re-retrieval of the same page."""
    key = f"{skill.strip().lower()}|{' '.join(question.lower().split())}"
    return f"{prefix}-{skill_key(skill)}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def pick_seeds(questions: Iterable[SourcedQuestion], skill: str, difficulty: int,
               used_ids: Iterable[str] = (), k: int = 3) -> List[SourcedQuestion]:
    """Up to ``k`` unused interview questions for ``skill``, closest to ``difficulty`` first."""
    used = set(used_ids)
    fresh = [q for q in questions if q.id not in used and skill_matches(q.skill, skill)]
    return sorted(fresh, key=lambda q: (abs(q.difficulty - difficulty), q.difficulty < difficulty, q.id))[:k]


def pick_quiz(mcqs: Iterable[SourcedMCQ], skill: str, difficulty: int, topics: Iterable[str] = (),
              used_ids: Iterable[str] = (), n: int = 4) -> List[SourcedMCQ]:
    """``n`` unused assessment questions for ``skill``, or [] if there are
    fewer (the caller then falls back to a model-written quiz). Prefers
    questions on the studied ``topics`` and near ``difficulty``, and spreads
    picks across page topics before taking two from the same one."""
    used = set(used_ids)
    fresh = [q for q in mcqs if q.id not in used and skill_matches(q.skill, skill)]
    if len(fresh) < n:
        return []
    studied = [_tokens(t) for t in topics]

    def overlap(q: SourcedMCQ) -> int:
        mine = _tokens(f"{q.topic} {q.question}")
        return max((len(mine & t) for t in studied), default=0)

    ranked = sorted(fresh, key=lambda q: (-overlap(q), abs(q.difficulty - difficulty), q.id))
    picked, seen_topics = [], set()
    for q in ranked:  # first pass: one per page topic
        key = q.topic.lower() or q.id
        if key not in seen_topics:
            picked.append(q)
            seen_topics.add(key)
        if len(picked) == n:
            return picked
    return picked + [q for q in ranked if q not in picked][: n - len(picked)]
