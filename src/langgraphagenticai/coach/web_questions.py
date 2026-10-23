"""Interview and assessment questions retrieved from the web.

The only source of sourced questions for assessments and interviews:

    search GeeksforGeeks / InterviewBit for "<skill> interview questions",
    getting each page's text from the search API (LangSearch, then Tavily),
    or else fetching the page and reducing it to plain text
    -> the LLM extracts questions from that text, each with a short quote
       from the page as evidence
    -> anything whose evidence is not actually on the page is dropped
    -> the rest become bank rows linked to the page, cached in SQLite

Pages are retrieved once per skill and shared by every candidate until the
cache expires, which keeps search and LLM quota use low. The cache is SQLite.

Key points and explanations are paraphrased; only the question, a link and
our summary are stored, never the page's answers.
"""
import json
import logging
import re
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FuturesTimeout
from html.parser import HTMLParser
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from src.langgraphagenticai.coach.questions import SourcedMCQ, SourcedQuestion, question_id

logger = logging.getLogger(__name__)

# Sites that publish interview questions with explanations, and their display names.
QUESTION_SITES = {"geeksforgeeks.org": "GeeksforGeeks", "interviewbit.com": "InterviewBit"}
PAGES_PER_SKILL = 2
PAGE_CHARS = 9000            # ~2.5k tokens per page: Groq's free tier allows ~8k tokens/minute
CACHE_DAYS = 30
EMPTY_CACHE_HOURS = 24       # pages had no usable questions: retry tomorrow
INCOMPLETE_CACHE_HOURS = 1   # an extraction call failed (e.g. rate limit, bad JSON): retry soon
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


# ---------------- LLM extraction schema ---------------- #

class _WebInterviewQ(BaseModel):
    question: str = Field(..., description="The interview question as the page asks it.")
    difficulty: int = Field(..., ge=1, le=5, description="1 = definition, 3 = applied, 5 = design trade-offs.")
    key_points: List[str] = Field(..., min_length=2, max_length=5,
                                  description="What a strong answer covers, in your own words, based only on the page.")
    evidence: str = Field(..., description="A short sentence copied exactly from the page that supports the key points.")


class _WebMCQ(BaseModel):
    question: str
    topic: str = Field("", description="Sub-topic, e.g. 'Joins'.")
    difficulty: int = Field(..., ge=1, le=5)
    options: List[str] = Field(..., min_length=4, max_length=4)
    answer_index: int = Field(..., ge=0, le=3)
    explanation: str = Field(..., description="One line, in your own words, on why the answer is correct.")
    evidence: str = Field(..., description="A short sentence copied exactly from the page that proves the answer.")


class _WebInterviewSet(BaseModel):
    interview: List[_WebInterviewQ] = Field(default_factory=list, max_length=8)


class _WebMCQSet(BaseModel):
    mcqs: List[_WebMCQ] = Field(default_factory=list, max_length=6)


class _MCQCheck(BaseModel):
    index: int
    answer_index: int = Field(..., ge=-1, le=3, description="0-based option the page supports; -1 if none does.")
    unambiguous: bool = Field(..., description="False if more than one option could be argued correct, or the question is unclear.")


class _MCQChecks(BaseModel):
    checks: List[_MCQCheck] = Field(default_factory=list)


# Questions that only make sense next to their source page ("which algorithm is
# mentioned first in the page?", "... as described?"). The candidate never sees
# the page, so these are unanswerable. "page" is not matched when it is the
# memory term (page table, page fault...), so OS questions are kept.
_DOC = (r"(?:page(?! (?:tables?|faults?|sizes?|replacement|frames?|cache|hit|miss|directory|entry|entries"
        r"|numbers?|files?|in|out|swap|swapping|boundary|loads?)\b)"
        r"|article|tutorial|post|passage|text|guide|blog)")
_SOURCE_REF = re.compile(
    r"\b(?:in|on|from|by|per) (?:the|this) " + _DOC + r"\b"
    r"|\baccording to (?:the|this) (?:author|source|" + _DOC + r")\b"
    r"|\bas (?:described|mentioned|discussed|explained|shown|listed|stated|defined)\b"
    r"|\bmentioned (?:first|last|earlier|above|below)\b"
    r"|\b(?:listed|shown|given|mentioned|described) (?:above|below)\b"
    r"|\b(?:does|do|did|would) (?:the|this) (?:author|" + _DOC + r")\b"
    r"|\b(?:the|this) " + _DOC + r"'s\b",
    re.IGNORECASE,
)


def refers_to_source(question: str) -> bool:
    """True if the question cannot be answered without seeing its source page."""
    return bool(_SOURCE_REF.search(question))


# ---------------- page fetching ---------------- #

_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer", "header", "aside", "form", "svg", "button"}
_BLOCK_TAGS = {"p", "div", "li", "br", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "section", "article"}


class _TextExtractor(HTMLParser):
    """Visible text of a page, preferring the <article> body when there is one."""

    def __init__(self):
        super().__init__()
        self.skip = 0
        self.in_article = 0
        self.all: List[str] = []
        self.article: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self.skip += 1
        elif tag == "article":
            self.in_article += 1
        if tag in _BLOCK_TAGS:
            self._add("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS and self.skip:
            self.skip -= 1
        elif tag == "article" and self.in_article:
            self.in_article -= 1

    def handle_data(self, data):
        if not self.skip:
            self._add(data)

    def _add(self, s: str):
        self.all.append(s)
        if self.in_article:
            self.article.append(s)

    def text(self) -> str:
        article = _tidy("".join(self.article))
        if len(article) > 1000:
            return article
        # No <article>: skip the menu of short link labels, starting just
        # before the first real paragraph (keeps the page title above it).
        lines = _tidy("".join(self.all)).split("\n")
        first = next((i for i, line in enumerate(lines) if len(line) > 120), 0)
        if first > len(lines) // 3:
            first = 0  # no clear menu block; keep everything
        return "\n".join(lines[max(first - 3, 0):])


def _tidy(s: str) -> str:
    lines = (" ".join(line.split()) for line in s.splitlines())
    return "\n".join(line for line in lines if line)


def fetch_text(url: str, timeout: int = 12, max_bytes: int = 3_000_000) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        if "html" not in (resp.headers.get("Content-Type") or ""):
            return ""
        raw = resp.read(max_bytes)
        charset = resp.headers.get_content_charset() or "utf-8"
    p = _TextExtractor()
    p.feed(raw.decode(charset, errors="replace"))
    return p.text()


def _norm(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", s.lower()))


def on_page(evidence: str, page_norm: str) -> bool:
    """True when the quoted evidence really is on the page (ignoring case,
    punctuation and spacing). Short quotes prove nothing, so they fail."""
    e = _norm(evidence)
    return len(e.split()) >= 5 and e in page_norm


def topic_name(skill: str) -> str:
    """The name pages use for a skill. Role tracks qualify skills in brackets,
    e.g. "Deep Learning (PyTorch/TensorFlow)": searched or prompted with the
    qualifier, a general Deep Learning page is judged off-topic and yields no
    questions. A one-word base is too vague ("Testing (pytest)"): use the
    qualifier instead."""
    base = re.sub(r"\s*\([^)]*\)", "", skill).strip()
    inner = re.findall(r"\(([^)]*)\)", skill)
    if inner and len(base.split()) < 2:
        return inner[0].strip()
    return base or skill


def _site(url: str) -> Optional[str]:
    return next((s for s in QUESTION_SITES if s in url.lower()), None)


def _relevant(hits: List[dict], skill: str) -> List[dict]:
    """Interview-question pages that name the skill (search also returns
    course ads and unrelated articles), best match first."""
    words = set(_norm(skill).split()) - {"and", "or", "the", "basics", "fundamentals"}

    def about(h: dict) -> str:
        # Path and title only: the host "interviewbit.com" itself contains "interview".
        path = urllib.parse.urlparse(h.get("url", "")).path
        return _norm(f"{path} {h.get('title', '')}")

    # Whole words: titles end in "- InterviewBit", which is not a question page.
    # The page must also name the skill: "R Interview Questions" is not a
    # Statistics page for a Python role, though search returns it for one.
    pages = [h for h in hits if {"interview", "interviews"} & set(about(h).split()) and "courses" not in about(h).split()
             and words & set(about(h).split())]
    return sorted(pages, key=lambda h: -len(words & set(about(h).split())))


# ---------------- harvester ---------------- #

Ask = Callable[[type, str], BaseModel]


class WebQuestions:
    """Retrieves, verifies and caches web questions per skill.

    search: a SourceSearch (anything with ``.web(query, site, n)``).
    fetch:  url -> page text; injectable for tests.
    """

    def __init__(self, search, db_path: str, fetch: Callable[[str], str] = fetch_text, workers: int = 2):
        self.search = search
        self.db_path = db_path
        self.fetch = fetch
        # Few workers: harvesting is LLM-heavy and Groq's free tier is rate-limited.
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="web-questions")
        self._inflight: Dict[str, Future] = {}
        self._lock = threading.Lock()
        with sqlite3.connect(db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS web_questions (
                    skill_key TEXT PRIMARY KEY,
                    skill TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    fetched_at REAL NOT NULL
                )
            """)

    @staticmethod
    def _key(skill: str) -> str:
        return _norm(skill)

    # ---- cache ----

    def _cached(self, skill: str) -> Optional[Tuple[List[SourcedQuestion], List[SourcedMCQ]]]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT payload, fetched_at FROM web_questions WHERE skill_key = ?",
                               (self._key(skill),)).fetchone()
        if not row:
            return None
        data = json.loads(row[0])
        if not data.get("complete", True):
            ttl = INCOMPLETE_CACHE_HOURS * 3600
        elif data["interview"] or data["mcqs"]:
            ttl = CACHE_DAYS * 86400
        else:
            ttl = EMPTY_CACHE_HOURS * 3600
        if time.time() - row[1] > ttl:
            return None
        return ([SourcedQuestion(**q) for q in data["interview"] if not refers_to_source(q["question"])],
                [SourcedMCQ(**q) for q in data["mcqs"] if not refers_to_source(q["question"])])

    def _save(self, skill: str, questions: List[SourcedQuestion], mcqs: List[SourcedMCQ],
              complete: bool = True) -> None:
        payload = json.dumps({"interview": [q.model_dump() for q in questions], "mcqs": [q.model_dump() for q in mcqs],
                              "complete": complete})
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO web_questions (skill_key, skill, payload, fetched_at) VALUES (?, ?, ?, ?)",
                         (self._key(skill), skill, payload, time.time()))

    # ---- public ----

    def harvest(self, skill: str, ask: Ask, wait: Optional[float] = 240) -> Tuple[List[SourcedQuestion], List[SourcedMCQ]]:
        """Web questions for ``skill``: from cache, from a retrieval already
        running, or retrieved now, waiting at most ``wait`` seconds (0 = cache
        only). A retrieval that outlasts the wait keeps running and fills the
        cache for next time. Never raises; returns ([], []) when nothing is
        ready."""
        cached = self._cached(skill)
        if cached is not None:
            return cached
        future = self._future(skill, ask)
        try:
            return future.result(timeout=wait)
        except FuturesTimeout:
            logger.info("web questions for %s not ready within %ss; continuing in the background", skill, wait)
            return [], []
        except Exception as e:
            logger.warning("web questions for %s failed: %s", skill, e)
            return [], []

    def prefetch(self, skills: List[str], ask: Ask) -> None:
        """Start retrieving in the background so later quizzes and interview
        questions find the cache warm."""
        for s in skills:
            if self._cached(s) is None:
                self._future(s, ask)

    def _future(self, skill: str, ask: Ask) -> Future:
        key = self._key(skill)
        with self._lock:
            f = self._inflight.get(key)
            if f is None:
                f = self._pool.submit(self._retrieve, skill, ask)
                f.add_done_callback(lambda _f, k=key: self._inflight.pop(k, None))
                self._inflight[key] = f
            return f

    # ---- retrieval ----

    def _pages(self, skill: str) -> List[dict]:
        """Up to PAGES_PER_SKILL pages, one per site where possible. Each has a
        url and, when the search API provided it, the page ``text``."""
        query = f"{topic_name(skill)} interview questions"
        with_text = getattr(self.search, "pages", None)
        hits = with_text(query, list(QUESTION_SITES), n=6, text_chars=PAGE_CHARS,
                         keep=lambda h: _relevant(h, skill)) if with_text else []
        if not hits:
            for site in QUESTION_SITES:
                hits += _relevant(self.search.web(query, site=site, n=3) or [], skill)[:1]
        by_site: Dict[str, dict] = {}
        for h in hits:
            site = _site(h.get("url", ""))
            if site and site not in by_site:
                by_site[site] = h
        picked = list(by_site.values())
        picked += [h for h in hits if h not in picked and _site(h.get("url", ""))]
        return picked[:PAGES_PER_SKILL]

    def _retrieve(self, skill: str, ask: Ask) -> Tuple[List[SourcedQuestion], List[SourcedMCQ]]:
        questions: List[SourcedQuestion] = []
        mcqs: List[SourcedMCQ] = []
        searched, complete = False, True
        for hit in self._pages(skill):
            searched = True
            url, site = hit["url"], _site(hit["url"])
            if not site:
                continue
            text = (hit.get("text") or "")[:PAGE_CHARS]
            if len(text) < PAGE_CHARS // 2:
                # Search APIs sometimes return only part of the page; the site
                # itself may block us, so keep whichever text is longer.
                try:
                    fetched = self.fetch(url)[:PAGE_CHARS]
                    text = fetched if len(fetched) > len(text) else text
                except Exception as e:
                    logger.info("could not fetch %s: %s", url, e)
            if len(text) < 500:
                continue
            q, m, ok = self._extract(skill, url, QUESTION_SITES[site], text, ask)
            complete = complete and ok
            # The same question on two sites gets the same id: keep the first.
            questions += [x for x in q if x.id not in {y.id for y in questions}]
            mcqs += [x for x in m if x.id not in {y.id for y in mcqs}]
        if searched:  # don't cache "nothing" when search itself was down
            self._save(skill, questions, mcqs, complete=complete)
        logger.info("web questions for %s: %d interview, %d assessment", skill, len(questions), len(mcqs))
        return questions, mcqs

    def _ask_page(self, ask: Ask, schema, task: str, skill: str, url: str, text: str):
        """One extraction call; None on failure. Interview and quiz questions are
        asked for separately: one long combined answer made the model drift into
        a markdown table instead of JSON, losing the whole page. ``skill`` is
        the topic_name."""
        try:
            return ask(schema, f"""
Below is the text of a web page about {skill} interview questions. Using ONLY this page:

{task}

Every question must stand on its own: the candidate will NOT see this page, so never ask what the page
mentions, lists first, or describes ("as described", "in the article", "according to the page").
For EVERY item, evidence must be one sentence copied exactly from the page that supports it.
Skip anything the page does not explain. Return an empty list if the page has no {skill} questions.

PAGE ({url}):
{text}
""")
        except Exception as e:
            logger.warning("%s extraction failed for %s: %s", schema.__name__, url, e)
            return None

    def _extract(self, skill: str, url: str, source: str, text: str, ask: Ask) -> Tuple[List[SourcedQuestion], List[SourcedMCQ]]:
        name = topic_name(skill)
        def interview():
            return self._ask_page(ask, _WebInterviewSet, f"""interview: up to 8 spoken interview questions on {name} that the page asks and answers.
Keep each question close to the page's wording. key_points: 2-5 points a strong answer covers, in your
own words, taken from the page's answer.""", name, url, text)

        def assessment():
            mq = self._ask_page(ask, _WebMCQSet, f"""mcqs: up to 6 multiple-choice questions on {name} testing facts the page explains. Four
distinct options of which EXACTLY ONE is correct and the other three are clearly wrong per the page.
answer_index is the 0-based correct option; explanation is one line in your own words that agrees with
the correct option's wording.""", name, url, text)
            return self._verify(ask, name, url, text, mq.mcqs) if mq and mq.mcqs else ([] if mq else None)

        # Side by side: one after the other they made a skill's retrieval take
        # minutes, longer than a candidate waits before taking the assessment.
        with ThreadPoolExecutor(max_workers=1) as side:
            pending = side.submit(interview)
            checked = assessment()
            iq = pending.result()
        out = SimpleNamespace(interview=iq.interview if iq else [], mcqs=checked or [])
        complete = iq is not None and checked is not None

        page = _norm(text)
        questions, mcqs = [], []
        for q in out.interview:
            if on_page(q.evidence, page) and not refers_to_source(q.question):
                questions.append(SourcedQuestion(
                    id=question_id("web-iq", skill, q.question), skill=skill, difficulty=q.difficulty, question=q.question,
                    key_points=q.key_points, source_name=source, source_url=url))
        for q in out.mcqs:
            if on_page(q.evidence, page) and len({o.strip().lower() for o in q.options}) == 4 \
                    and not refers_to_source(q.question):
                mcqs.append(SourcedMCQ(
                    id=question_id("web-mcq", skill, q.question), skill=skill, topic=q.topic, difficulty=q.difficulty,
                    question=q.question, options=q.options, answer_index=q.answer_index,
                    explanation=q.explanation, source_name=source, source_url=url))
        dropped = len(out.interview) + len(out.mcqs) - len(questions) - len(mcqs)
        if dropped:
            logger.info("dropped %d unverified questions from %s", dropped, url)
        return questions, mcqs, complete

    def _verify(self, ask: Ask, skill: str, url: str, text: str, mcqs: List[_WebMCQ]) -> Optional[List[_WebMCQ]]:
        """Answer each MCQ again from the page, without the answer key; keep
        only those where the second answer agrees and the question is
        unambiguous. None if the check itself failed."""
        listing = "\n".join(f"[{i}] {q.question}\n" + "\n".join(f"  {j}) {o}" for j, o in enumerate(q.options))
                            for i, q in enumerate(mcqs))
        try:
            res = ask(_MCQChecks, f"""
Answer each multiple-choice question below using the page text that follows. For each, give the
0-based index of the option the page supports (-1 if none), and set unambiguous=false if more than one
option could reasonably be argued correct, the question is unclear, the question cannot be answered
without seeing this page (it asks what the page mentions first, says "as described", "in the article"),
or the page's answer is factually wrong in general (pages contain mistakes, e.g. "zero covariance means
independence").

QUESTIONS:
{listing}

PAGE ({url}):
{text}
""")
        except Exception as e:
            logger.warning("MCQ check failed for %s: %s", url, e)
            return None
        by_index = {c.index: c for c in res.checks}
        kept = [q for i, q in enumerate(mcqs)
                if i in by_index and by_index[i].unambiguous and by_index[i].answer_index == q.answer_index]
        if len(kept) < len(mcqs):
            logger.info("MCQ check dropped %d of %d questions from %s", len(mcqs) - len(kept), len(mcqs), url)
        return kept
