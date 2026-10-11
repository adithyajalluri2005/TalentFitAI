"""Nodes of the coaching graph.

Nodes that wait on the candidate (``await_*``) do nothing but call
``interrupt()``. LangGraph re-runs a node from the top when it resumes, so any
LLM call placed before the interrupt would run twice; generating content and
waiting for the answer are therefore always separate nodes.
"""
import difflib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, List, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.langgraphagenticai.coach import scoring
from src.langgraphagenticai.coach.search import is_trusted
from src.langgraphagenticai.coach.state import (
    CheckpointResult, CoachState, InterviewTurn, Observation, SkillTopics, Topic,
    QuizQuestion, ReadinessSnapshot, Resource, RoleSkill, RubricScore, SkillLevel,
)

logger = logging.getLogger(__name__)

# Seconds to wait between retries after a rate-limit error.
RATE_LIMIT_BACKOFF = (10, 20, 40)


# ---------------- LLM output schemas ---------------- #

class _JDProfile(BaseModel):
    target_role: str
    skills: List[RoleSkill] = Field(..., min_length=3, max_length=10)


class _ResumeRating(BaseModel):
    skill: str
    resume_level: int = Field(..., ge=0, le=5, description="0 = no evidence, 3 = works independently, 5 = expert.")
    evidence: List[str] = Field(default_factory=list, description="Verbatim resume phrases supporting resume_level.")


class _ResumeRatings(BaseModel):
    ratings: List[_ResumeRating]


class _TopicDraft(BaseModel):
    title: str = Field(..., description="Specific concept, e.g. 'Autograd and backpropagation in PyTorch'.")
    why: str = Field(..., description="One short line: why the role needs it.")
    query: str = Field(..., description="Precise web search query for a free, high-quality resource on exactly this topic.")


class _SkillOutline(BaseModel):
    skill: str
    official_docs_site: str = Field("", description="Domain of the skill's official docs, e.g. 'pytorch.org'; empty if none.")
    github_query: str = Field("", description="2-4 keywords for GitHub repos that teach the skill, e.g. 'pytorch tutorial'.")
    language: str = Field("", description="Programming language the role uses for this skill, as GitHub names it (e.g. 'Python', 'Java', 'JavaScript'); empty if not language-specific.")
    topics: List[_TopicDraft] = Field(..., min_length=1, max_length=5)


class _Outline(BaseModel):
    skills: List[_SkillOutline]


class _Pick(BaseModel):
    key: str = Field(..., description="Topic key, e.g. 't3'.")
    picks: List[str] = Field(default_factory=list, description="Candidate ids chosen for this topic, best first, e.g. ['t3.2', 't3.0']. Empty if none are good.")


class _Curation(BaseModel):
    topics: List[_Pick]


class _Quiz(BaseModel):
    questions: List[QuizQuestion] = Field(..., min_length=3, max_length=5)


class _Question(BaseModel):
    question: str


class _Evaluation(BaseModel):
    score: RubricScore
    feedback: str = Field(..., description="Two or three sentences: what was good, what was missing.")
    needs_follow_up: bool = Field(..., description="True if the answer was vague or partly wrong and a probing question would reveal more.")


class _Adjustment(BaseModel):
    turn_index: int
    score: RubricScore
    reason: str


class _Critique(BaseModel):
    adjustments: List[_Adjustment] = Field(default_factory=list)


class _Summary(BaseModel):
    summary: str
    next_steps: List[str] = Field(..., max_length=5)


def _is_daily_limit(e: Exception) -> bool:
    msg = str(e).lower()
    return "per day" in msg or "(tpd)" in msg or "(rpd)" in msg


def _is_rate_limit(e: Exception) -> bool:
    # Groq's 429 can arrive wrapped by LangChain, so match the status/message, not the class.
    msg = str(e).lower()
    return type(e).__name__ == "RateLimitError" or "429" in msg or "rate limit" in msg


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _skill(state: CoachState, name: str) -> SkillLevel:
    return next(s for s in state.skills if s.skill == name)


class CoachNodes:
    def __init__(
        self,
        llm,
        search: Optional[Callable[[str], list]] = None,
        on_snapshot: Optional[Callable[[CoachState, str, ReadinessSnapshot], None]] = None,
        fallback_llm=None,
    ):
        """
        llm: a LangChain chat model supporting ``with_structured_output``.
        fallback_llm: used when ``llm`` is out of quota for the day (it has its
            own quota on Groq), so a session keeps working instead of failing.
        search: a SourceSearch (or test double) with .topic(query, official_site)
            and .skill(skill, github_query); plan sources come only from it,
            never from URLs the model writes.
        on_snapshot: called with (state, thread_id, snapshot) after each re-score.
        """
        self.llm = llm
        self.fallback_llm = fallback_llm
        self.search = search
        self.on_snapshot = on_snapshot

    def _ask(self, schema, prompt: str):
        # JSON mode first: reasoning models on Groq (gpt-oss) often answer in
        # plain text instead of calling a tool ("tool_use_failed"), which wastes
        # a call. Tool calling stays as the fallback.
        json_prompt = (f"{prompt}\n\nRespond with ONLY a JSON object matching this JSON Schema:\n"
                       f"{json.dumps(schema.model_json_schema())}")
        last_error = None
        for llm in [m for m in (self.llm, self.fallback_llm) if m is not None]:
            attempts = [
                (llm.with_structured_output(schema, method="json_mode"), json_prompt),
                (llm.with_structured_output(schema), prompt),
            ]
            out_of_quota = False
            for chain, text in attempts:
                for wait in RATE_LIMIT_BACKOFF + (None,):
                    try:
                        result = chain.invoke(text)
                        return result if isinstance(result, schema) else schema.model_validate(result)
                    except Exception as e:
                        last_error = e
                        if _is_daily_limit(e):
                            # Waiting won't help for hours: move to the fallback model now.
                            logger.warning("daily quota exhausted for %s; switching model", schema.__name__)
                            out_of_quota = True
                            break
                        # Groq's free tier allows ~8k tokens/minute, which one coaching
                        # cycle can exceed; waiting it out beats failing the session.
                        if wait is not None and _is_rate_limit(e):
                            logger.info("rate limited on %s; retrying in %ss", schema.__name__, wait)
                            time.sleep(wait)
                            continue
                        logger.warning("structured output failed for %s: %s", schema.__name__, e)
                        break
                if out_of_quota:
                    break
            if not out_of_quota:
                break  # a non-quota failure: the fallback model would not do better
        raise last_error

    # ---------------- diagnose ---------------- #

    def rate_resume(self, resume_text: str, role_skills: List[RoleSkill]) -> List[SkillLevel]:
        """Rate a resume on a fixed list of skills. Also used on its own to
        compare a resume against every role track in one call."""
        r = self._ask(_ResumeRatings, f"""
You are a career coach. Rate the candidate's demonstrated level in EACH skill below, using only
evidence in the resume; quote that evidence verbatim. A skill used in a described project counts
as evidence even if it is not listed under "Skills". Closely related experience counts partially
(e.g. Flask experience is partial evidence for FastAPI). Rate 0 when there is no evidence.
Calibrate strictly — a resume claims, it does not prove:
- only named in a skills list, never shown in use: at most 1
- used in one project or course: 2
- used in several projects, an internship, or with concrete outcomes: 3
- 4-5 only for sustained professional use or clearly advanced work.
Return exactly one rating per skill, using the skill names exactly as given.

SKILLS: {[s.skill for s in role_skills]}

RESUME:
{resume_text[:6000]}
""")
        by_name = {x.skill.lower(): x for x in r.ratings}
        skills = []
        for rs in role_skills:
            match = difflib.get_close_matches(rs.skill.lower(), list(by_name), n=1, cutoff=0.6)
            rating = by_name[match[0]] if match else None
            baseline = float(rating.resume_level) if rating else 0.0
            evidence = rating.evidence if rating else []
            skills.append(SkillLevel(
                skill=rs.skill, required_level=rs.required_level, jd_weight=rs.jd_weight,
                baseline=baseline, level=baseline, evidence=evidence,
                observations=[Observation(source="resume", value=baseline, note="; ".join(evidence)[:300])],
            ))
        return skills

    def diagnose(self, state: CoachState) -> dict:
        role_skills, role = state.role_skills, state.target_role
        if not role_skills:
            # Pasted JD: extract the role's skill profile first.
            d = self._ask(_JDProfile, f"""
Extract the 5-10 skills that matter most for this job, with the level the job needs
(1 = aware, 3 = works independently, 5 = expert) and importance (1 = core, 0.2 = nice to have).
Use short canonical skill names (e.g. "Docker", "SQL", "System Design").

JOB DESCRIPTION:
{state.jd_text[:6000]}
""")
            role_skills, role = d.skills, role or d.target_role
        skills = self.rate_resume(state.resume_text, role_skills)
        return {"skills": skills, "role_skills": role_skills, "target_role": role, "status": "learning"}

    # ---------------- plan ---------------- #

    # Skills covered per plan; the plan is revised after every re-score, so
    # later cycles pick up the rest.
    MAX_PLAN_SKILLS = 4
    MAX_TOPICS = 4

    def plan(self, state: CoachState) -> dict:
        gaps = sorted((s for s in state.skills if s.gap > 0), key=scoring.priority, reverse=True)[:self.MAX_PLAN_SKILLS]
        if not gaps:
            return {"plan": [], "checkpoint_queue": []}

        outline = self._outline(state, gaps)
        candidates, snippets = self._search(outline)
        picks = self._curate(outline, candidates, snippets, state.target_role) if candidates else {}

        def chosen(key: str, fallback_types: tuple) -> List[Resource]:
            if key in picks:
                return picks[key]
            # Curation unavailable: first TRUSTED search hit of each wanted type.
            # Raw search results can include spam, so an unvetted link is never shown.
            out = []
            for want in fallback_types:
                hit = next((r for r in candidates.get(key, [])
                            if r.type in want and r not in out and is_trusted(r)), None)
                if hit:
                    out.append(hit)
            return out

        plan = []
        for si, sk in enumerate(outline):
            topics = [
                Topic(title=t.title, why=t.why, resources=chosen(f"t{si}.{ti}", (("docs", "article"), ("video",))))
                for ti, t in enumerate(sk.topics)
            ]
            plan.append(SkillTopics(skill=sk.skill, topics=topics,
                                    resources=chosen(f"s{si}", (("course",), ("github",)))))
        return {"plan": plan, "checkpoint_queue": [p.skill for p in plan], "status": "learning"}

    def _outline(self, state: CoachState, gaps: List[SkillLevel]) -> List[_SkillOutline]:
        gap_lines = "\n".join(
            f"- {s.skill}: current level {s.level:.1f}/5, role needs {s.required_level}/5"
            + (f"; resume shows: {'; '.join(s.evidence)[:160]}" if s.evidence else "; no evidence on resume")
            for s in gaps
        )
        recap = ""
        weak = [t.question for t in state.interview if t.score and t.score.average < 3][-4:]
        if state.history and weak:
            recap = ("\nThis is a revised plan after a mock interview. Cover what the candidate got wrong:\n"
                     + "\n".join(f"- {q}" for q in weak) + "\n")

        o = self._ask(_Outline, f"""
You are a senior engineer mentoring a fresher for the role: {state.target_role}.
For EACH skill below, list the {self.MAX_TOPICS - 1}-{self.MAX_TOPICS} topics they must study to move from their current level to
the level the role needs, in learning order. Skip basics the resume already proves. Topics must be specific
concepts an interviewer would test (e.g. "Autograd and backpropagation in PyTorch", "SQL window functions"),
not vague areas ("Learn PyTorch", "Advanced topics").
{recap}
For every topic write a search query that finds a great free tutorial or video on exactly that topic:
- 3-7 words: the technology + the specific concept, e.g. "PyTorch autograd tutorial", "SQL window functions explained"
- never generic ("learn python", "best resources for X", "top courses")
For every skill also give:
- official_docs_site: the domain of its official documentation if it has one (e.g. "pytorch.org", "docs.python.org");
  empty for broad subjects like statistics
- github_query: 2-4 keywords that find popular GitHub repos for LEARNING it (tutorials, exercises, curated lists),
  e.g. "pytorch tutorial", "sql exercises", "statistics python notebooks"
- language: the programming language THIS ROLE would practise the skill in, as GitHub names it
  (e.g. Data Structures & Algorithms for a Python Backend role -> "Python"; for a Java role -> "Java");
  empty for language-neutral skills like SQL, statistics or system design

Use the skill names EXACTLY as given.
SKILLS:
{gap_lines}
""")
        # Snap skill names back to the diagnosed ones so checkpoints line up,
        # and keep priority order rather than the model's order.
        names = {s.skill.lower(): s.skill for s in gaps}
        out = {}
        for sk in o.skills:
            m = difflib.get_close_matches(sk.skill.lower(), list(names), n=1, cutoff=0.5)
            if m and names[m[0]] not in out:
                out[names[m[0]]] = sk.model_copy(update={"skill": names[m[0]], "topics": sk.topics[:self.MAX_TOPICS]})
        return [out[s.skill] for s in gaps if s.skill in out]

    def _search(self, outline: List[_SkillOutline]) -> tuple:
        """(key -> [Resource] candidates in relevance order, url -> snippet).
        Keys: "s{i}" = skill-wide (courses, repos), "t{i}.{j}" = one topic."""
        snippets = {}
        if not self.search:
            return {}, snippets
        jobs = {}
        for si, sk in enumerate(outline):
            jobs[f"s{si}"] = (self.search.skill, sk.skill, sk.github_query, sk.language)
            for ti, t in enumerate(sk.topics):
                jobs[f"t{si}.{ti}"] = (self.search.topic, t.query, sk.official_docs_site)
        results = {}
        # Modest parallelism: free search backends throttle bursts.
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(job[0], *job[1:]): key for key, job in jobs.items()}
            for f in as_completed(futures):
                key = futures[f]
                try:
                    hits = [r for r in f.result() if r.get("url")]
                    results[key] = [Resource(**{k: r.get(k, "") for k in ("title", "url", "type", "source", "meta")})
                                    for r in hits]
                    snippets.update({r["url"]: r.get("snippet", "") for r in hits})
                except Exception as e:
                    logger.warning("source search failed for %s: %s", key, e)
        return results, snippets

    def _curate(self, outline: List[_SkillOutline], candidates: dict, snippets: dict, target_role: str = "") -> dict:
        """LLM picks the best sources, only from search results. One call per
        skill keeps each request under Groq's per-request token cap. Returns
        key -> [Resource]; keys whose curation failed are absent, so callers
        fall back to search order for them."""
        out = {}
        for si, sk in enumerate(outline):
            keys = [(f"s{si}", f"{sk.skill} — whole-skill course / repo")] + \
                   [(f"t{si}.{ti}", t.title) for ti, t in enumerate(sk.topics)]
            blocks = []
            for key, label in keys:
                cands = candidates.get(key, [])[:8]
                if not cands:
                    continue
                lines = "\n".join(
                    f"  {key}.{ci} [{r.type}] {r.title[:90]} — {r.url}"
                    + (f" ({r.meta})" if r.meta else "")
                    + (f"\n      {snippets[r.url][:110]}" if snippets.get(r.url) else "")
                    for ci, r in enumerate(cands)
                )
                blocks.append(f"{key} | {label}\n{lines}")
            if not blocks:
                continue
            state_role = target_role or "the target role"
            lang_rule = f", i.e. {sk.language}" if sk.language else " or be language-neutral"
            try:
                c = self._ask(_Curation, f"""
You are a senior engineer curating FREE study material on {sk.skill} for a fresher.

For the whole-skill key (s{si}): pick up to 2 — the best free full COURSE (a university/MOOC course or a long
YouTube course from a reputable channel) and the best GitHub repo for LEARNING (tutorials, exercises,
notebooks, curated lists). The repo's language is shown after the stars: it MUST match the role
({state_role}){lang_rule}. Reject repos that are the library's own source code, unrelated tools or
general "everything" lists.

For each topic key (t...): pick up to 2 — ideally ONE written source (official docs/tutorial first, then
a respected tutorial site like Real Python, Baeldung, GeeksforGeeks, MDN, freeCodeCamp) and ONE YouTube video
that teaches exactly that topic (prefer official channels and well-known educators; views and length are
shown — favour clear, popular explanations over tiny or clickbait ones).

REJECT: roundups/listicles, paid-only courses, release notes, blog announcements, mirrors or copies of
official docs on other domains, old versions when a current one exists, and anything not about the topic.
One excellent pick beats a weak second; return an empty list when nothing is good.

Return one entry per key, candidate ids exactly as shown (e.g. "t{si}.0.2"), best first.

{chr(10).join(blocks)}
""")
            except Exception as e:
                logger.warning("source curation failed for %s: %s", sk.skill, e)
                continue
            for p in c.topics:
                cands = candidates.get(p.key, [])[:8]
                chosen = []
                for cid in p.picks:
                    prefix, _, idx = cid.rpartition(".")
                    if prefix == p.key and idx.isdigit() and int(idx) < len(cands) and cands[int(idx)] not in chosen:
                        chosen.append(cands[int(idx)])
                out[p.key] = chosen[:2]
        return out

    # ---------------- checkpoint quiz ---------------- #

    def make_checkpoint(self, state: CoachState) -> dict:
        skill = _skill(state, state.checkpoint_queue[0])
        topics = [t.title for p in state.plan if p.skill == skill.skill for t in p.topics][:4]
        scope = ("Write ONE question for EACH of these study topics, in order:\n"
                 + "\n".join(f"- {t}" for t in topics)) if topics else "Cover the skill broadly."
        quiz = self._ask(_Quiz, f"""
Write a skill assessment: 4 multiple-choice questions checking whether a candidate has reached level
{skill.required_level}/5 in {skill.skill} for a {state.target_role} role. The candidate has just studied the
topics below. {scope}
Use realistic, applied scenarios (code snippets welcome), not trivia or definitions.
Each question has exactly 4 options; answer_index is the 0-based index of the correct option;
explanation says briefly why it is correct.
""")
        return {"current_quiz_skill": skill.skill, "current_quiz": quiz.questions, "quiz_answers": [], "switch_to": None}

    def await_checkpoint(self, state: CoachState) -> dict:
        reply = interrupt({
            "type": "checkpoint",
            "skill": state.current_quiz_skill,
            "topics": [t.model_dump() for p in state.plan if p.skill == state.current_quiz_skill for t in p.topics],
            "questions": [{"question": q.question, "options": q.options} for q in state.current_quiz],
            "pending": list(state.checkpoint_queue),
            "accepts": {"answers": "list[int]", "action": "'skip' | 'skip_all' | 'switch' (with skill)"},
        }) or {}
        action = reply.get("action")
        if action == "switch" and reply.get("skill") in state.checkpoint_queue \
                and reply["skill"] != state.current_quiz_skill:
            target = reply["skill"]
            return {"checkpoint_queue": [target] + [s for s in state.checkpoint_queue if s != target],
                    "switch_to": target, "quiz_answers": []}
        if action == "skip_all":
            return {"skip_checkpoints": True, "quiz_answers": []}
        if action == "skip":
            return {"quiz_answers": []}
        return {"quiz_answers": [int(a) for a in reply.get("answers", [])]}

    def grade_checkpoint(self, state: CoachState) -> dict:
        name = state.current_quiz_skill
        queue = [s for s in state.checkpoint_queue if s != name]
        if not state.quiz_answers:
            result = CheckpointResult(skill=name, cycle=state.cycle, score=0, skipped=True)
            return {"checkpoints": state.checkpoints + [result], "checkpoint_queue": queue}

        correct = sum(
            1 for q, a in zip(state.current_quiz, state.quiz_answers) if q.answer_index == a
        )
        score = correct / len(state.current_quiz)
        skills = [s.model_copy(deep=True) for s in state.skills]
        sk = next(s for s in skills if s.skill == name)
        sk.observations.append(Observation(
            source="checkpoint", cycle=state.cycle,
            value=scoring.checkpoint_observation(score, sk.required_level),
            note=f"{correct}/{len(state.current_quiz)} on checkpoint quiz",
        ))
        sk.level = scoring.skill_level(sk, state.cycle)
        result = CheckpointResult(skill=name, cycle=state.cycle, score=round(score, 2))
        return {"skills": skills, "checkpoints": state.checkpoints + [result], "checkpoint_queue": queue}

    # ---------------- adaptive interview ---------------- #

    def _cycle_turns(self, state: CoachState) -> List[InterviewTurn]:
        return state.interview[-self._turns_this_cycle(state):] if self._turns_this_cycle(state) else []

    @staticmethod
    def _turns_this_cycle(state: CoachState) -> int:
        return len(state.interview) - state.cycle * state.interview_turns

    def interview_ask(self, state: CoachState) -> dict:
        turns = self._cycle_turns(state)
        last = turns[-1] if turns else None

        if last and last.needs_follow_up and not last.is_follow_up:
            skill, follow_up = _skill(state, last.skill), True
        else:
            asked = {t.skill: 0 for t in turns}
            for t in turns:
                asked[t.skill] += 1
            # Highest-priority skill, rotated so one weak skill does not take every turn.
            skill = max(state.skills, key=lambda s: (scoring.priority(s) + s.jd_weight * 0.5) / (1 + asked.get(s.skill, 0)))
            follow_up = False

        difficulty = max(1, min(5, round(skill.level) + 1))
        context = ""
        if follow_up:
            context = f"""This is a FOLLOW-UP. Previous question: {last.question}
Candidate answered: {last.answer}
Interviewer's note: {last.feedback}
Probe the specific weak point; do not repeat the question."""

        q = self._ask(_Question, f"""
You are interviewing a candidate for: {state.target_role}.
Ask ONE spoken-interview question on {skill.skill} at difficulty {difficulty}/5
(1 = definitions, 3 = applied scenario, 5 = design trade-offs under constraints).
It must be answerable verbally in about two minutes. Prefer scenarios over trivia.
{context}
Questions already asked (do not repeat): {[t.question for t in turns]}
""")
        turn = InterviewTurn(skill=skill.skill, difficulty=difficulty, question=q.question, is_follow_up=follow_up)
        return {"interview": state.interview + [turn], "status": "interviewing"}

    def await_answer(self, state: CoachState) -> dict:
        turn = state.interview[-1]
        reply = interrupt({
            "type": "interview_question",
            "turn": self._turns_this_cycle(state),
            "of": state.interview_turns,
            "skill": turn.skill,
            "difficulty": turn.difficulty,
            "is_follow_up": turn.is_follow_up,
            "question": turn.question,
            "accepts": {"answer": "str", "voice_metrics": "dict[str, float] (optional)"},
        }) or {}
        updated = turn.model_copy(update={
            "answer": (reply.get("answer") or "").strip() or "NO_ANSWER",
            "voice_metrics": reply.get("voice_metrics") or {},
        })
        return {"interview": state.interview[:-1] + [updated]}

    @staticmethod
    def _voice_note(turn: InterviewTurn) -> str:
        m = turn.voice_metrics
        if not m:
            return ""
        parts = []
        if m.get("duration_seconds"):
            parts.append(f"{m.get('words_per_minute', 0):.0f} words/min (comfortable is ~120-160), "
                         f"{m.get('filler_words', 0):.0f} filler words in {m.get('duration_seconds', 0):.0f}s")
        if "eye_contact_pct" in m:
            parts.append(f"looked at the camera {m['eye_contact_pct']:.0f}% of the time, "
                         f"face visible {m.get('face_visible_pct', 0):.0f}% of the time (camera interview)")
        if not parts:
            return ""
        return "DELIVERY: " + "; ".join(parts) + ". Factor delivery into communication only, never correctness."

    def interview_eval(self, state: CoachState) -> dict:
        turn = state.interview[-1]
        if turn.answer == "NO_ANSWER":
            ev = _Evaluation(score=RubricScore(correctness=1, depth=1, communication=1),
                             feedback="No answer given.", needs_follow_up=False)
        else:
            ev = self._ask(_Evaluation, f"""
You are a fair, strict technical interviewer. Score this spoken answer (transcribed, so ignore
transcription errors) on a 1-5 rubric for a difficulty-{turn.difficulty} question on {turn.skill}.
correctness: is it technically right? depth: reasoning, trade-offs, examples? communication: clear and structured?

QUESTION: {turn.question}
ANSWER: {turn.answer}
{self._voice_note(turn)}""")
        updated = turn.model_copy(update={
            "score": ev.score, "feedback": ev.feedback, "needs_follow_up": ev.needs_follow_up,
        })
        return {"interview": state.interview[:-1] + [updated]}

    # ---------------- critic + re-score ---------------- #

    def critic(self, state: CoachState) -> dict:
        turns = self._cycle_turns(state)
        start = len(state.interview) - len(turns)
        transcript = "\n\n".join(
            f"[{i}] {t.skill} (difficulty {t.difficulty})\nQ: {t.question}\nA: {t.answer}\n"
            f"Score: correctness {t.score.correctness}, depth {t.score.depth}, communication {t.score.communication}\n"
            f"Feedback: {t.feedback}"
            for i, t in enumerate(turns)
        )
        c = self._ask(_Critique, f"""
You review another interviewer's scoring for consistency and fairness.
Flag only turns where the score is clearly wrong: generous scores for vague or incorrect answers,
harsh scores for correct answers, or inconsistent scoring between similar answers.
Return an adjustment ONLY for those turns (turn_index is the number in brackets). Return none if scoring is fair.

{transcript}
""")
        interview = list(state.interview)
        for adj in c.adjustments:
            if 0 <= adj.turn_index < len(turns):
                idx = start + adj.turn_index
                interview[idx] = interview[idx].model_copy(update={"score": adj.score, "critic_note": adj.reason})
        return {"interview": interview}

    def rescore(self, state: CoachState, config: RunnableConfig) -> dict:
        turns = self._cycle_turns(state)
        skills = [s.model_copy(deep=True) for s in state.skills]
        by_name = {s.skill: s for s in skills}
        for t in turns:
            if t.score and t.skill in by_name:
                by_name[t.skill].observations.append(Observation(
                    source="interview", cycle=state.cycle,
                    value=scoring.interview_observation(t.score.average, t.difficulty),
                    note=f"difficulty {t.difficulty}, rubric avg {t.score.average:.1f}" + (f" (critic: {t.critic_note})" if t.critic_note else ""),
                ))
        for s in skills:
            s.level = scoring.skill_level(s, state.cycle)

        snap = ReadinessSnapshot(
            cycle=state.cycle, readiness=scoring.readiness(skills),
            per_skill={s.skill: s.level for s in skills}, at=_now(),
        )
        if self.on_snapshot:
            try:
                self.on_snapshot(state, config.get("configurable", {}).get("thread_id", ""), snap)
            except Exception as e:  # history is a nice-to-have; never fail the session for it
                logger.warning("failed to record progress snapshot: %s", e)
        return {"skills": skills, "history": state.history + [snap]}

    def summarize(self, state: CoachState) -> dict:
        snap = state.history[-1]
        ready = snap.readiness >= state.target_readiness
        trend = " -> ".join(f"{h.readiness}%" for h in state.history)
        weak = sorted(state.skills, key=scoring.priority, reverse=True)[:3]
        s = self._ask(_Summary, f"""
You are a warm but honest career coach. Summarise this coaching cycle for the candidate in 3-4 sentences,
then give up to 5 concrete next steps. Refer to specific interview answers where useful.
Target role: {state.target_role}. Readiness trend: {trend} (target {state.target_readiness}%).
Weakest skills now: {[(w.skill, w.level, w.required_level) for w in weak]}
Interview feedback this cycle: {[(t.skill, t.feedback) for t in self._cycle_turns(state)]}
""")
        done = ready or state.cycle + 1 >= state.max_cycles
        return {
            "summary": s.summary, "next_steps": s.next_steps,
            "status": "ready" if ready else ("finished" if done else "learning"),
            # Next cycle starts fresh: new plan, new checkpoints.
            "cycle": state.cycle if done else state.cycle + 1,
            "skip_checkpoints": False,
        }

    # ---------------- routers ---------------- #

    @staticmethod
    def route_after_await(state: CoachState) -> str:
        return "make_checkpoint" if state.switch_to else "grade_checkpoint"

    @staticmethod
    def route_learning(state: CoachState) -> str:
        if state.checkpoint_queue and not state.skip_checkpoints:
            return "make_checkpoint"
        return "interview_ask"

    def route_interview(self, state: CoachState) -> str:
        return "interview_ask" if self._turns_this_cycle(state) < state.interview_turns else "critic"

    @staticmethod
    def route_after_cycle(state: CoachState) -> str:
        return "end" if state.status in ("ready", "finished") else "plan"
