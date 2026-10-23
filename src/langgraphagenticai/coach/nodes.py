"""Nodes of the coaching graph.

Nodes that wait on the candidate (``await_*``) do nothing but call
``interrupt()``. LangGraph re-runs a node from the top when it resumes, so any
LLM call placed before the interrupt would run twice; generating content and
waiting for the answer are therefore always separate nodes.
"""
import difflib
import functools
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt
from pydantic import BaseModel, Field, create_model

from src.langgraphagenticai.coach import scoring
from src.langgraphagenticai.coach.questions import pick_quiz, pick_seeds
from src.langgraphagenticai.coach.search import is_trusted
from src.langgraphagenticai.coach.state import (
    CheckpointResult, CoachState, InterviewTurn, Observation, SkillTopics, Topic,
    QuizQuestion, QuizReview, ReadinessSnapshot, Resource, RoleSkill, RubricScore, SkillLevel,
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


class _QuizItem(BaseModel):
    # Separate from QuizQuestion so the model is never offered source fields to invent.
    question: str
    options: List[str] = Field(..., min_length=4, max_length=4)
    answer_index: int = Field(..., ge=0, le=3)
    explanation: str = ""


class _Quiz(BaseModel):
    questions: List[_QuizItem] = Field(..., min_length=1)


@functools.lru_cache(maxsize=None)
def _quiz_schema(n: int) -> type:
    """_Quiz that must hold at least ``n`` questions, so a short reply fails
    validation and is retried instead of shrinking the assessment. A couple
    extra are allowed (models overshoot) and trimmed by the caller."""
    return create_model("_Quiz", __base__=_Quiz,
                        questions=(List[_QuizItem], Field(..., min_length=n, max_length=n + 2)))


class _Question(BaseModel):
    question: str
    seed: int = Field(-1, description="Number of the seed question your question is built on, or -1 if no seeds were given.")
    key_points: List[str] = Field(default_factory=list, description="2-5 points a strong answer covers. Leave empty only when asking a seed as-is or lightly reworded.")


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


_JSON_REMINDER = ("\n\nYour reply must be a single valid JSON object and nothing else: no markdown, "
                  "no tables, no text before or after it.")


def _is_bad_output(e: Optional[Exception]) -> bool:
    """The model answered, but not in the requested shape (invalid JSON, plain
    text instead of a tool call, or JSON that fails the schema)."""
    if e is None:
        return False
    msg = str(e).lower()
    return (type(e).__name__ in ("ValidationError", "OutputParserException", "JSONDecodeError")
            or any(k in msg for k in ("json_validate_failed", "tool_use_failed", "failed to generate json",
                                      "did not call a tool", "invalid json")))


def _is_rate_limit(e: Exception) -> bool:
    # Groq's 429 can arrive wrapped by LangChain, so match the status/message, not the class.
    msg = str(e).lower()
    return type(e).__name__ == "RateLimitError" or "429" in msg or "rate limit" in msg


def _unescape(text: str) -> str:
    """Models sometimes write line breaks as a literal backslash-n inside JSON
    strings, which would show up as backslash-n text in a code snippet. Turn
    them back into real line breaks (and tabs). Also drops LaTeX thousands
    separators ("10\\,000" -> "10,000")."""
    return (text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "    ")
            .replace("\\,", ","))


def _unescape_quiz(q: dict) -> dict:
    return {**q, "question": _unescape(q["question"]), "options": [_unescape(o) for o in q["options"]],
            "explanation": _unescape(q.get("explanation", ""))}


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
        web_questions=None,
    ):
        """
        llm: a LangChain chat model supporting ``with_structured_output``.
        fallback_llm: a model, or a list of models, tried in order when the
            ones before it are out of quota or rate limited, e.g. the same
            model on other Groq API keys, then a smaller model. A session keeps
            working instead of failing.
        search: a SourceSearch (or test double) with .topic(query, official_site)
            and .skill(skill, github_query); plan sources come only from it,
            never from URLs the model writes.
        on_snapshot: called with (state, thread_id, snapshot) after the re-score.
        web_questions: a WebQuestions retriever: questions from GeeksforGeeks /
            InterviewBit pages, each linked to its page. They seed the
            interviewer and make up assessments; without enough of them the
            model writes the questions (with no source).
        """
        self.llm = llm
        if fallback_llm is None:
            self.fallbacks = []
        elif isinstance(fallback_llm, (list, tuple)):
            self.fallbacks = [m for m in fallback_llm if m is not None]
        else:
            self.fallbacks = [fallback_llm]
        # Model index -> time until which it is skipped (out of quota or rate
        # limited), so calls go straight to the next one instead of each paying
        # a refused round trip first.
        self._paused: Dict[int, float] = {}
        self.search = search
        self.on_snapshot = on_snapshot
        self.web_questions = web_questions
        # sha1(resume) -> (time, {skill.lower(): rating}): "Which role suits me?" and the
        # session that follows rate the same resume, and must agree on it.
        self._ratings: Dict[str, tuple] = {}

    PRIMARY_QUOTA_PAUSE = 15 * 60  # seconds to skip a model after a daily-quota error
    RATE_LIMIT_PAUSE = 60          # seconds to skip a model after a per-minute limit, when others are left

    def _ask(self, schema, prompt: str):
        # JSON mode first: reasoning models on Groq (gpt-oss) often answer in
        # plain text instead of calling a tool ("tool_use_failed"), which wastes
        # a call. Tool calling stays as the fallback.
        json_prompt = (f"{prompt}\n\nRespond with ONLY a JSON object matching this JSON Schema:\n"
                       f"{json.dumps(schema.model_json_schema())}")
        last_error = None
        chain_all = list(enumerate([self.llm, *self.fallbacks]))
        now = time.time()
        # Paused models are skipped; if all are paused, try them all anyway.
        models = [(i, m) for i, m in chain_all if self._paused.get(i, 0) <= now] or chain_all
        for pos, (idx, llm) in enumerate(models):
            others_left = pos < len(models) - 1
            attempts = [
                (llm.with_structured_output(schema, method="json_mode"), json_prompt),
                (llm.with_structured_output(schema), prompt),
                # Bad output is often a one-off (the same prompt usually works on
                # the next try), so give JSON mode one more go with a firmer
                # reminder before failing the step, e.g. a whole session start.
                (llm.with_structured_output(schema, method="json_mode"), json_prompt + _JSON_REMINDER),
            ]
            out_of_quota = False
            for n, (chain, text) in enumerate(attempts):
                if n == len(attempts) - 1 and not _is_bad_output(last_error):
                    break  # the retry only helps with malformed output
                for wait in RATE_LIMIT_BACKOFF + (None,):
                    try:
                        result = chain.invoke(text)
                        return result if isinstance(result, schema) else schema.model_validate(result)
                    except Exception as e:
                        last_error = e
                        if _is_daily_limit(e):
                            # Waiting won't help for hours: move to the next model/key now.
                            logger.warning("daily quota exhausted for %s (model %d); switching", schema.__name__, idx)
                            out_of_quota = True
                            self._paused[idx] = time.time() + self.PRIMARY_QUOTA_PAUSE
                            break
                        if _is_rate_limit(e) and others_left:
                            # Another key or model is free right now: use it instead of waiting.
                            logger.info("rate limited on %s (model %d); switching", schema.__name__, idx)
                            out_of_quota = True
                            self._paused[idx] = time.time() + self.RATE_LIMIT_PAUSE
                            break
                        # Groq's free tier allows ~8k tokens/minute, which one coaching
                        # session can exceed; waiting it out beats failing the session.
                        if wait is not None and _is_rate_limit(e):
                            logger.info("rate limited on %s; retrying in %ss", schema.__name__, wait)
                            time.sleep(wait)
                            continue
                        logger.warning("structured output failed for %s: %s", schema.__name__, e)
                        break
                if out_of_quota:
                    break
            if not out_of_quota:
                break  # a non-quota failure: the next model would not do better
        raise last_error

    # ---------------- diagnose ---------------- #

    RATINGS_TTL = 6 * 3600

    def rate_resume(self, resume_text: str, role_skills: List[RoleSkill]) -> List[SkillLevel]:
        """Rate a resume on a fixed list of skills. Also used on its own to
        compare a resume against every role track in one call.

        Ratings are remembered per resume and skill for a few hours, so the
        same resume gets the same rating wherever it is shown (role
        suggestions, then the session); only skills not yet rated go to the
        model."""
        key = hashlib.sha1(resume_text.encode()).hexdigest()
        now = time.time()
        self._ratings = {k: v for k, v in self._ratings.items() if now - v[0] < self.RATINGS_TTL}
        known = self._ratings.get(key, (now, {}))[1]
        todo = [rs for rs in role_skills if rs.skill.lower() not in known]
        if todo:
            known = {**known, **self._rate(resume_text, todo)}
            self._ratings[key] = (now, known)

        skills = []
        for rs in role_skills:
            rating = known.get(rs.skill.lower())
            baseline = float(rating.resume_level) if rating else 0.0
            evidence = rating.evidence if rating else []
            skills.append(SkillLevel(
                skill=rs.skill, required_level=rs.required_level, jd_weight=rs.jd_weight,
                baseline=baseline, level=baseline, evidence=evidence,
                observations=[Observation(source="resume", value=baseline, note="; ".join(evidence)[:300])],
            ))
        return skills

    def _rate(self, resume_text: str, role_skills: List[RoleSkill]) -> Dict[str, Optional["_ResumeRating"]]:
        """One model call: {skill.lower(): rating or None when the model skipped it}."""
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
        out = {}
        for rs in role_skills:
            match = difflib.get_close_matches(rs.skill.lower(), list(by_name), n=1, cutoff=0.6)
            out[rs.skill.lower()] = by_name[match[0]] if match else None
        return out

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

    # Skills covered by the plan, highest priority first.
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
        # No questions are generated or retrieved here, not even in the
        # background: that would use up the model's rate limit while the
        # candidate studies. Each assessment is built when the candidate asks
        # for it, and interview questions when the interview starts.
        return {"plan": plan, "checkpoint_queue": [p.skill for p in plan], "status": "learning"}

    def _outline(self, state: CoachState, gaps: List[SkillLevel]) -> List[_SkillOutline]:
        gap_lines = "\n".join(
            f"- {s.skill}: current level {s.level:.1f}/5, role needs {s.required_level}/5"
            + (f"; resume shows: {'; '.join(s.evidence)[:160]}" if s.evidence else "; no evidence on resume")
            for s in gaps
        )
        o = self._ask(_Outline, f"""
You are a senior engineer mentoring a fresher for the role: {state.target_role}.
For EACH skill below, list the {self.MAX_TOPICS - 1}-{self.MAX_TOPICS} topics they must study to move from their current level to
the level the role needs, in learning order. Skip basics the resume already proves. Topics must be specific
concepts an interviewer would test (e.g. "Autograd and backpropagation in PyTorch", "SQL window functions"),
not vague areas ("Learn PyTorch", "Advanced topics").

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
        fall back to search order for them.

        The per-skill calls run in parallel: one after another they were the
        slowest part of building a plan."""
        def one(si: int, sk: _SkillOutline) -> dict:
            out = {}
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
                return out
            state_role = target_role or "the target role"
            lang_rule = f", i.e. {sk.language}" if sk.language else " or be language-neutral"
            try:
                c = self._ask(_Curation, f"""
You are a senior engineer curating FREE study material on {sk.skill} for a fresher.

For the whole-skill key (s{si}): pick up to 2 — the best free full COURSE (a university/MOOC course or a long
YouTube course from a reputable channel) and the best GitHub repo for LEARNING (tutorials, exercises,
notebooks, curated lists). The repo's language is shown after the stars: it MUST match the role
({state_role}){lang_rule}. Reject repos that are the library's own source code, unrelated tools,
general "everything" lists, repos not written in English, and repos teaching one narrow application
(e.g. web scraping, a single game) when the skill is general.

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
                return out
            for p in c.topics:
                cands = candidates.get(p.key, [])[:8]
                chosen = []
                for cid in p.picks:
                    prefix, _, idx = cid.rpartition(".")
                    if prefix == p.key and idx.isdigit() and int(idx) < len(cands) and cands[int(idx)] not in chosen:
                        chosen.append(cands[int(idx)])
                out[p.key] = chosen[:2]
            return out

        out = {}
        with ThreadPoolExecutor(max_workers=max(1, len(outline))) as pool:
            for picks in pool.map(lambda args: one(*args), enumerate(outline)):
                out.update(picks)
        return out

    # ---------------- checkpoint quiz ---------------- #

    # Seconds an assessment waits for web questions not yet retrieved for its
    # skill before using a model-written quiz (retrieval goes on in the
    # background and serves the next candidate).
    QUIZ_WEB_WAIT = 25
    # Questions in every assessment: web questions first, the model writes the rest.
    QUIZ_SIZE = 10

    @staticmethod
    def retakeable(state: CoachState) -> List[str]:
        """Plan skills whose assessment was taken (or skipped) and can be taken again."""
        taken = {c.skill for c in state.checkpoints}
        return [p.skill for p in state.plan if p.skill in taken and p.skill not in state.checkpoint_queue]

    def await_study(self, state: CoachState) -> dict:
        """Wait while the candidate studies. Nothing is generated until they
        ask for a skill's assessment ('assess'), retake one ('retake'), or
        start the final interview ('interview' once every assessment is done,
        'skip_all' to skip the ones still pending).

        After the interview the candidate comes back here: assessments can
        still be taken and retaken (each one re-scores readiness), and
        'finish' ends the session. There is one interview per session."""
        done = state.interview_done
        reply = interrupt({
            "type": "study",
            "pending": list(state.checkpoint_queue),
            "retakeable": self.retakeable(state),
            "interview_done": done,
            "accepts": {"action": "'assess' | 'retake' (with skill) | 'finish'" if done
                        else "'assess' | 'retake' (with skill) | 'interview' | 'skip_all'"},
        }) or {}
        action, target = reply.get("action"), reply.get("skill")
        if action == "assess" and target in state.checkpoint_queue:
            return {"checkpoint_queue": [target] + [s for s in state.checkpoint_queue if s != target],
                    "switch_to": target}
        if action == "retake" and target in self.retakeable(state):
            return {"checkpoint_queue": [target] + list(state.checkpoint_queue), "switch_to": target}
        if done:
            return {"closed": True} if action == "finish" else {}
        if action == "skip_all" or (action == "interview" and not state.checkpoint_queue):
            return {"skip_checkpoints": True}
        return {}

    @staticmethod
    def route_after_study(state: CoachState) -> str:
        if state.closed:
            return "end"
        if state.skip_checkpoints and not state.interview_done:
            return "interview_ask"
        return "make_checkpoint" if state.switch_to else "await_study"

    def make_checkpoint(self, state: CoachState) -> dict:
        skill = _skill(state, state.checkpoint_queue[0])
        topics = [t.title for p in state.plan if p.skill == skill.skill for t in p.topics][:4]
        # Questions from earlier attempts, so a retake gets new ones.
        earlier = [r for c in state.checkpoints if c.skill == skill.skill for r in c.review]
        attempt = sum(1 for c in state.checkpoints if c.skill == skill.skill)
        questions = []
        if self.web_questions:
            pool = self.web_questions.harvest(skill.skill, self._ask, wait=self.QUIZ_WEB_WAIT)[1]
            picked = pick_quiz(pool, skill.skill, skill.required_level, topics,
                               used_ids=[r.bank_id for r in earlier if r.bank_id], n=self.QUIZ_SIZE)
            for q in picked:
                options, answer = q.shuffled(seed=f"{state.candidate_id}|{attempt}")
                questions.append(QuizQuestion(
                    question=q.question, options=options, answer_index=answer, explanation=q.explanation,
                    bank_id=q.id, source_name=q.source_name, source_url=q.source_url,
                ))

        missing = self.QUIZ_SIZE - len(questions)
        if missing:
            # Sites rarely give a full quiz's worth of verified questions for a
            # skill: the model writes the rest, so every assessment is the same size.
            scope = ("Spread the questions evenly across these study topics:\n"
                     + "\n".join(f"- {t}" for t in topics)) if topics else "Cover the skill broadly."
            avoid = ""
            if questions:
                avoid += ("\nThe assessment already has these questions. Do not repeat or lightly reword them:\n"
                          + "\n".join(f"- {q.question}" for q in questions))
            if earlier:
                avoid += ("\nThis is a retake. Do not reuse or lightly reword these earlier questions:\n"
                          + "\n".join(f"- {r.question}" for r in earlier))
            quiz = self._ask(_quiz_schema(missing), f"""
Write a skill assessment: exactly {missing} multiple-choice questions checking whether a candidate has reached level
{skill.required_level}/5 in {skill.skill} for a {state.target_role} role. The candidate has just studied the
topics below. {scope}
Use realistic, applied scenarios (code snippets welcome), not trivia or definitions. Put any code in a
fenced ``` block with real line breaks.
Each question has exactly 4 options; answer_index is the 0-based index of the correct option;
explanation says briefly why it is correct.{avoid}
""")
            questions += [QuizQuestion(**_unescape_quiz(q.model_dump())) for q in quiz.questions[:missing]]
        return {"current_quiz_skill": skill.skill, "current_quiz": questions, "quiz_answers": [], "switch_to": None}

    def await_checkpoint(self, state: CoachState) -> dict:
        reply = interrupt({
            "type": "checkpoint",
            "skill": state.current_quiz_skill,
            "topics": [t.model_dump() for p in state.plan if p.skill == state.current_quiz_skill for t in p.topics],
            "questions": [{"question": q.question, "options": q.options, "source_name": q.source_name,
                           "source_url": q.source_url} for q in state.current_quiz],
            "pending": list(state.checkpoint_queue),
            "interview_done": state.interview_done,
            "accepts": {"answers": "list[int]", "action": "'skip' | 'skip_all' | 'switch' (with skill)"},
        }) or {}
        action = reply.get("action")
        if action == "switch" and reply.get("skill") in state.checkpoint_queue \
                and reply["skill"] != state.current_quiz_skill:
            target = reply["skill"]
            return {"checkpoint_queue": [target] + [s for s in state.checkpoint_queue if s != target],
                    "switch_to": target, "quiz_answers": []}
        if action == "skip_all" and not state.interview_done:
            return {"skip_checkpoints": True, "quiz_answers": []}
        if action in ("skip", "skip_all"):
            return {"quiz_answers": []}
        return {"quiz_answers": [int(a) for a in reply.get("answers", [])]}

    def grade_checkpoint(self, state: CoachState, config: RunnableConfig = None) -> dict:
        name = state.current_quiz_skill
        queue = [s for s in state.checkpoint_queue if s != name]
        if not state.quiz_answers:
            if any(c.skill == name for c in state.checkpoints):
                # A skipped retake: the earlier result still stands.
                return {"checkpoint_queue": queue, "current_quiz": []}
            result = CheckpointResult(skill=name, cycle=state.cycle, score=0, skipped=True)
            return {"checkpoints": state.checkpoints + [result], "checkpoint_queue": queue}

        correct = sum(
            1 for q, a in zip(state.current_quiz, state.quiz_answers) if q.answer_index == a
        )
        score = correct / len(state.current_quiz)
        skills = [s.model_copy(deep=True) for s in state.skills]
        sk = next(s for s in skills if s.skill == name)
        # A retake replaces the earlier attempt: the latest score is what counts.
        sk.observations = [o for o in sk.observations if o.source != "checkpoint"]
        sk.observations.append(Observation(
            source="checkpoint", cycle=state.cycle,
            value=scoring.checkpoint_observation(score, sk.required_level),
            note=f"{correct}/{len(state.current_quiz)} on checkpoint quiz",
        ))
        sk.level = scoring.skill_level(sk, state.cycle)
        review = [QuizReview(**q.model_dump(), chosen=a) for q, a in zip(state.current_quiz, state.quiz_answers)]
        result = CheckpointResult(skill=name, cycle=state.cycle, score=round(score, 2), review=review)
        out = {"skills": skills, "checkpoints": state.checkpoints + [result], "checkpoint_queue": queue}
        if state.interview_done:
            # After the interview an assessment changes the final result: record
            # the new readiness and let it make the candidate interview-ready.
            snap = self._snapshot(state, skills, config)
            ready = snap.readiness >= state.target_readiness
            out.update({"history": state.history + [snap], "status": "ready" if ready else "finished"})
        return out

    def _snapshot(self, state: CoachState, skills: List[SkillLevel], config: Optional[RunnableConfig]) -> ReadinessSnapshot:
        snap = ReadinessSnapshot(
            cycle=state.cycle, readiness=scoring.readiness(skills),
            per_skill={s.skill: s.level for s in skills}, at=_now(),
        )
        if self.on_snapshot:
            try:
                self.on_snapshot(state, (config or {}).get("configurable", {}).get("thread_id", ""), snap)
            except Exception as e:  # history is a nice-to-have; never fail the session for it
                logger.warning("failed to record progress snapshot: %s", e)
        return snap

    # ---------------- adaptive interview ---------------- #

    # Seconds the first interview question waits for its skill's web questions
    # before the model asks without seeds.
    INTERVIEW_WEB_WAIT = 25

    @staticmethod
    def _next_skill(skills: List[SkillLevel], asked: Dict[str, int]) -> SkillLevel:
        # Highest-priority skill, rotated so one weak skill does not take every turn.
        return max(skills, key=lambda s: (scoring.priority(s) + s.jd_weight * 0.5) / (1 + asked.get(s.skill, 0)))

    def _interview_skills(self, state: CoachState) -> List[str]:
        """The skills the main interview questions will be on, in order."""
        asked: Dict[str, int] = {}
        for _ in range(state.interview_turns):
            s = self._next_skill(state.skills, asked).skill
            asked[s] = asked.get(s, 0) + 1
        return list(asked)

    def interview_ask(self, state: CoachState) -> dict:
        turns = state.interview
        last = turns[-1] if turns else None

        if not turns and self.web_questions and hasattr(self.web_questions, "prefetch"):
            # The interview is starting: retrieve web questions for every skill it
            # will cover. The later skills are ready while the first is answered.
            try:
                self.web_questions.prefetch(self._interview_skills(state), self._ask)
            except Exception as e:  # questions then come from the model; never fail the interview for it
                logger.warning("web question prefetch failed: %s", e)

        if last and last.needs_follow_up and not last.is_follow_up:
            skill, follow_up = _skill(state, last.skill), True
        else:
            asked = {t.skill: 0 for t in turns}
            for t in turns:
                asked[t.skill] += 1
            skill = self._next_skill(state.skills, asked)
            follow_up = False

        difficulty = max(1, min(5, round(skill.level) + 1))
        context, seeds = "", []
        if follow_up:
            context = f"""This is a FOLLOW-UP. Previous question: {last.question}
Candidate answered: {last.answer}
Interviewer's note: {last.feedback}
Probe the specific weak point; do not repeat the question."""
        else:
            if self.web_questions:
                # The first question waits briefly for retrieval; later ones read
                # what is ready (retrieval started with the interview) and never
                # keep the candidate waiting mid-interview.
                wait = 0 if turns else self.INTERVIEW_WEB_WAIT
                web = self.web_questions.harvest(skill.skill, self._ask, wait=wait)[0]
                seeds = pick_seeds(web, skill.skill, difficulty, used_ids=[t.bank_id for t in state.interview])
        if seeds:
            context = (f"SEED QUESTIONS from interview-prep sites. Build your question on ONE of them and set seed to its number.\n"
                       f"- Seed at difficulty {difficulty} or above: ask it as-is or lightly reworded, and leave key_points empty.\n"
                       f"- Seed below difficulty {difficulty}: keep its concept but raise it to {difficulty} (an applied scenario,\n"
                       f"  a failure to debug, or a trade-off), and write key_points for your harder version.\n"
                       + "\n".join(f"[{i}] (difficulty {q.difficulty}) {q.question}" for i, q in enumerate(seeds)))
        else:
            context += "\nAlso list in key_points the 2-5 points a strong answer would cover."

        q = self._ask(_Question, f"""
You are interviewing a candidate for: {state.target_role}.
Ask ONE spoken-interview question on {skill.skill} at difficulty {difficulty}/5
(1 = definitions, 3 = applied scenario, 5 = design trade-offs under constraints).
It must be answerable verbally in about two minutes. Prefer scenarios over trivia.
{context}
Questions already asked (do not repeat): {[t.question for t in turns]}
""")
        seed = seeds[q.seed] if 0 <= q.seed < len(seeds) else None
        # A seed raised to a harder version comes with its own key points; the
        # seed's page still explains the concept, so its source link is kept.
        raised = bool(seed and q.key_points)
        turn = InterviewTurn(
            skill=skill.skill, difficulty=difficulty if (raised or not seed) else seed.difficulty,
            question=q.question, is_follow_up=follow_up, bank_id=seed.id if seed else "",
            key_points=q.key_points[:5] if (raised or not seed) else seed.key_points,
            source_name=seed.source_name if seed else "", source_url=seed.source_url if seed else "",
        )
        return {"interview": state.interview + [turn], "status": "interviewing"}

    def await_answer(self, state: CoachState) -> dict:
        turn = state.interview[-1]
        reply = interrupt({
            "type": "interview_question",
            # Main questions so far: a follow-up keeps its question's number.
            "turn": sum(1 for t in state.interview if not t.is_follow_up),
            "of": state.interview_turns,
            "skill": turn.skill,
            "difficulty": turn.difficulty,
            "is_follow_up": turn.is_follow_up,
            "question": turn.question,
            "source_name": turn.source_name,
            "source_url": turn.source_url,
            "accepts": {"answer": "str", "voice_metrics": "dict[str, float] (optional)", "action": "'skip' | 'end'"},
        }) or {}
        if reply.get("action") == "end":
            # Ending early: the unanswered question is dropped, so only answered
            # questions count; questions never asked do not count against the candidate.
            return {"interview": state.interview[:-1], "interview_ended": True}
        if reply.get("action") == "skip":
            return {"interview": state.interview[:-1] + [turn.model_copy(update={"answer": "SKIPPED"})]}
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

    @staticmethod
    def _key_points_note(turn: InterviewTurn) -> str:
        if not turn.key_points:
            return ""
        return ("REFERENCE KEY POINTS (a strong answer covers these; other correct, relevant points also count):\n"
                + "\n".join(f"- {p}" for p in turn.key_points)
                + "\nBase correctness and depth on how many points are covered correctly; name missed points in feedback.")

    def interview_eval(self, state: CoachState) -> dict:
        turn = state.interview[-1]
        if turn.answer in ("NO_ANSWER", "SKIPPED"):
            # A skipped question scores like an unanswered one and gets no follow-up.
            ev = _Evaluation(score=RubricScore(correctness=1, depth=1, communication=1),
                             feedback="Question skipped." if turn.answer == "SKIPPED" else "No answer given.",
                             needs_follow_up=False)
        else:
            ev = self._ask(_Evaluation, f"""
You are a fair, strict technical interviewer. Score this spoken answer (transcribed, so ignore
transcription errors) on a 1-5 rubric for a difficulty-{turn.difficulty} question on {turn.skill}.
correctness: is it technically right? depth: reasoning, trade-offs, examples? communication: clear and structured?

QUESTION: {turn.question}
{self._key_points_note(turn)}
ANSWER: {turn.answer}
{self._voice_note(turn)}""")
        updated = turn.model_copy(update={
            "score": ev.score, "feedback": ev.feedback, "needs_follow_up": ev.needs_follow_up,
        })
        return {"interview": state.interview[:-1] + [updated]}

    # ---------------- critic + re-score ---------------- #

    def critic(self, state: CoachState) -> dict:
        turns = state.interview
        if not turns:  # interview ended before any answer: nothing to review
            return {}
        transcript = "\n\n".join(
            f"[{i}] {t.skill} (difficulty {t.difficulty})\nQ: {t.question}\n"
            + (f"Key points: {'; '.join(t.key_points)}\n" if t.key_points else "")
            + f"A: {t.answer}\n"
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
                idx = adj.turn_index
                interview[idx] = interview[idx].model_copy(update={"score": adj.score, "critic_note": adj.reason})
        return {"interview": interview}

    def rescore(self, state: CoachState, config: RunnableConfig) -> dict:
        turns = state.interview
        skills = [s.model_copy(deep=True) for s in state.skills]
        by_name = {s.skill: s for s in skills}
        for t in turns:
            if t.score and t.skill in by_name:
                by_name[t.skill].observations.append(Observation(
                    source="interview", cycle=state.cycle,
                    # No answer is no evidence of skill: level 0, not the rubric floor of 1.
                    value=0.0 if t.answer in ("SKIPPED", "NO_ANSWER") else scoring.interview_observation(t.score.average, t.difficulty),
                    note=("skipped" if t.answer == "SKIPPED" else "no answer" if t.answer == "NO_ANSWER"
                          else f"difficulty {t.difficulty}, rubric avg {t.score.average:.1f}") + (f" (critic: {t.critic_note})" if t.critic_note else ""),
                ))
        for s in skills:
            s.level = scoring.skill_level(s, state.cycle)

        snap = self._snapshot(state, skills, config)
        return {"skills": skills, "history": state.history + [snap]}

    def summarize(self, state: CoachState) -> dict:
        snap = state.history[-1]
        ready = snap.readiness >= state.target_readiness
        trend = " -> ".join(f"{h.readiness}%" for h in state.history)
        weak = sorted(state.skills, key=scoring.priority, reverse=True)[:3]
        s = self._ask(_Summary, f"""
You are a warm but honest career coach. Summarise this coaching session for the candidate in 3-4 sentences,
then give up to 5 concrete next steps. Refer to specific interview answers where useful.
Target role: {state.target_role}. Readiness trend: {trend} (target {state.target_readiness}%).
Weakest skills now: {[(w.skill, w.level, w.required_level) for w in weak]}
Interview feedback: {[(t.skill, t.feedback) for t in state.interview]}
""")
        # Pending assessments skipped for the interview can still be taken now.
        return {"summary": s.summary, "next_steps": s.next_steps, "status": "ready" if ready else "finished",
                "skip_checkpoints": False}

    @staticmethod
    def route_after_summary(state: CoachState) -> str:
        """Back to the plan for post-interview assessments; without a plan there are none."""
        return "await_study" if state.plan else "end"

    # ---------------- routers ---------------- #

    @staticmethod
    def route_after_answer(state: CoachState) -> str:
        return "critic" if state.interview_ended else "interview_eval"

    @staticmethod
    def route_after_await(state: CoachState) -> str:
        return "make_checkpoint" if state.switch_to else "grade_checkpoint"

    @staticmethod
    def route_learning(state: CoachState) -> str:
        # With a plan, the candidate stays on it (studying, taking and retaking
        # assessments) until they start the interview.
        if state.plan and (not state.skip_checkpoints or state.interview_done):
            return "await_study"
        return "interview_ask"

    def route_interview(self, state: CoachState) -> str:
        """interview_turns main questions; follow-ups come on top of them, so
        a weak answer to the last question still gets its follow-up."""
        last = state.interview[-1]
        main = sum(1 for t in state.interview if not t.is_follow_up)
        if main < state.interview_turns or (last.needs_follow_up and not last.is_follow_up):
            return "interview_ask"
        return "critic"
