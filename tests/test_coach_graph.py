"""Drives a whole coaching session through every interrupt with a scripted LLM."""
import re

from src.langgraphagenticai.coach import nodes as N
from src.langgraphagenticai.coach import scoring
from src.langgraphagenticai.coach.graph import CoachGraph
from src.langgraphagenticai.coach.nodes import CoachNodes
from src.langgraphagenticai.coach.state import (
    CoachState, Observation, QuizQuestion, RoleSkill, RubricScore, SkillLevel,
)
from src.langgraphagenticai.coach.roles import RoleStore, SEED_ROLES


class FakeLLM:
    """Returns canned structured output per schema; interview scores improve
    when the answer contains 'good'."""

    def __init__(self):
        self.calls = []

    def with_structured_output(self, schema, **kwargs):
        llm = self

        class Chain:
            def invoke(self, prompt):
                llm.calls.append(schema.__name__)
                return llm.respond(schema, prompt)
        return Chain()

    def respond(self, schema, prompt):
        if schema is N._JDProfile:
            return N._JDProfile(target_role="Backend Dev", skills=[
                RoleSkill(skill="Python", required_level=3, jd_weight=1.0),
                RoleSkill(skill="Docker", required_level=3, jd_weight=0.8),
                RoleSkill(skill="SQL", required_level=3, jd_weight=0.6),
            ])
        if schema is N._ResumeRatings:
            # Model paraphrases one name ("python 3") and omits Docker entirely.
            return N._ResumeRatings(ratings=[
                N._ResumeRating(skill="python 3", resume_level=3, evidence=["Built Flask APIs"]),
                N._ResumeRating(skill="SQL", resume_level=1),
            ])
        if schema is N._Outline:
            # Reversed order + paraphrased name: the node must restore both.
            return N._Outline(skills=[
                N._SkillOutline(skill="sql", topics=[N._TopicDraft(title="Joins", why="w", query="SQL joins tutorial")]),
                N._SkillOutline(skill="Docker", official_docs_site="docs.docker.com", topics=[
                    N._TopicDraft(title="Images", why="w", query="Docker images tutorial"),
                    N._TopicDraft(title="Compose", why="w", query="Docker compose guide"),
                ]),
            ])
        if schema is N._Curation:
            # t0.0 = Docker/Images: pick #1 then #0; t0.1: an id from another topic (ignored);
            # t1.0: nothing good.
            # Called once per skill. Skill 0 (Docker): course+repo for the skill,
            # two picks for Images (one out of range, ignored), a cross-topic id
            # for Compose (rejected). Skill 1 (SQL): curator finds nothing good.
            if "on Docker" in prompt:
                return N._Curation(topics=[
                    N._Pick(key="s0", picks=["s0.1", "s0.0"]),
                    N._Pick(key="t0.0", picks=["t0.0.1", "t0.0.0", "t0.0.9"]),
                    N._Pick(key="t0.1", picks=["t1.0.0"]),
                ])
            return N._Curation(topics=[N._Pick(key="t1.0", picks=[])])
        if issubclass(schema, N._Quiz):
            n = int(re.search(r"exactly (\d+) multiple-choice", prompt).group(1))
            return schema(questions=[N._QuizItem(question=f"q{i}", options=["a", "b", "c", "d"], answer_index=0) for i in range(n)])
        if schema is N._Question:
            return N._Question(question=f"question {prompt.count('FOLLOW-UP')}")
        if schema is N._Evaluation:
            good = "ANSWER: good" in prompt
            s = 5 if good else 2
            return N._Evaluation(score=RubricScore(correctness=s, depth=s, communication=s),
                                 feedback="ok", needs_follow_up=not good)
        if schema is N._Critique:
            return N._Critique()
        if schema is N._Summary:
            return N._Summary(summary="summary", next_steps=["practice"])
        raise AssertionError(schema)


def _state(**kw):
    return CoachState(candidate_id="c1", resume_text="resume", jd_text="jd", interview_turns=3, **kw)


def test_session_is_single_pass_with_retakes_and_records_history():
    snapshots = []
    llm = FakeLLM()
    coach = CoachGraph(CoachNodes(llm, on_snapshot=lambda s, t, snap: snapshots.append((t, snap))))
    view = coach.start("t1", _state(target_readiness=85))
    # Diagnosis + plan only: no quiz is written until the candidate asks for one.
    assert view["waiting_for"] == {"type": "study", "pending": ["Docker", "SQL"], "retakeable": [], "interview_done": False,   # highest weight x gap first
                                   "accepts": {"action": "'assess' | 'retake' (with skill) | 'interview' | 'skip_all'"}}
    assert "_Quiz" not in llm.calls
    start_readiness = view["readiness"]

    view = coach.respond("t1", {"action": "assess", "skill": "Docker"})
    assert view["waiting_for"]["type"] == "checkpoint" and view["waiting_for"]["skill"] == "Docker"
    assert "answer_index" not in str(view["waiting_for"])      # answers hidden from client
    assert view["waiting_for"]["questions"][0]["source_url"] == ""   # model-written: no source
    assert "current_quiz" not in view["state"]

    view = coach.respond("t1", {"answers": [1] * 5 + [0] * 5})       # Docker: half right
    assert view["waiting_for"]["type"] == "study" and view["waiting_for"]["pending"] == ["SQL"]
    assert view["waiting_for"]["retakeable"] == ["Docker"]
    half = view["readiness"]
    assert half > start_readiness                              # live score moves on checkpoint

    # Retake Docker: the new score replaces the old one.
    view = coach.respond("t1", {"action": "retake", "skill": "Docker"})
    assert view["waiting_for"]["type"] == "checkpoint" and view["waiting_for"]["skill"] == "Docker"
    view = coach.respond("t1", {"answers": [0] * 10})
    assert view["readiness"] > half
    docker = next(s for s in view["state"]["skills"] if s["skill"] == "Docker")
    assert [o["source"] for o in docker["observations"]] == ["resume", "checkpoint"]
    assert [c["score"] for c in view["state"]["checkpoints"]] == [0.5, 1.0]

    view = coach.respond("t1", {"action": "interview"})        # SQL still pending: ignored
    assert view["waiting_for"]["type"] == "study"
    view = coach.respond("t1", {"action": "assess", "skill": "SQL"})
    view = coach.respond("t1", {"action": "skip"})              # SQL: skipped
    # Every assessment done: stays on the plan until the interview is started.
    assert view["waiting_for"]["type"] == "study" and view["waiting_for"]["pending"] == []
    assert view["waiting_for"]["retakeable"] == ["Docker", "SQL"]
    view = coach.respond("t1", {"action": "interview"})
    assert view["waiting_for"]["type"] == "interview_question"

    view = coach.respond("t1", {"answer": "meh"})
    assert view["waiting_for"]["is_follow_up"] is True
    assert view["waiting_for"]["turn"] == 1                     # a follow-up keeps its question's number
    view = coach.respond("t1", {"answer": "meh"})               # no follow-up on a follow-up
    assert view["waiting_for"]["turn"] == 2 and not view["waiting_for"]["is_follow_up"]
    view = coach.respond("t1", {"answer": "good answer"})
    assert view["waiting_for"]["turn"] == 3
    view = coach.respond("t1", {"answer": "good answer"})

    # 3 main questions plus 1 follow-up: summarized, no re-plan, back on the plan.
    assert view["done"] is False
    assert view["state"]["status"] in ("ready", "finished") and view["state"]["cycle"] == 0
    assert len(view["state"]["history"]) == 1 and view["state"]["summary"]
    w = view["waiting_for"]
    assert w["type"] == "study" and w["interview_done"] is True and w["retakeable"] == ["Docker", "SQL"]

    # Assessments after the interview: the skipped SQL one now counts and re-scores readiness.
    view = coach.respond("t1", {"action": "interview"})          # one interview per session: ignored
    assert view["waiting_for"]["type"] == "study"
    view = coach.respond("t1", {"action": "retake", "skill": "SQL"})
    assert view["waiting_for"]["type"] == "checkpoint" and view["waiting_for"]["interview_done"] is True
    view = coach.respond("t1", {"action": "skip_all"})           # no interview to skip to: just a skip
    assert view["waiting_for"]["type"] == "study"
    assert [c["skipped"] for c in view["state"]["checkpoints"] if c["skill"] == "SQL"] == [True]
    before = view["state"]["history"][-1]["readiness"]
    view = coach.respond("t1", {"action": "retake", "skill": "SQL"})
    view = coach.respond("t1", {"answers": [0] * 10})
    h = view["state"]["history"]
    assert len(h) == 2 and h[-1]["readiness"] > before
    assert view["waiting_for"]["type"] == "study"

    view = coach.respond("t1", {"action": "finish"})
    assert view["done"] is True
    assert [t for t, _ in snapshots] == ["t1", "t1"]


def test_respond_when_not_waiting_raises():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    coach.start("t2", _state())
    coach.respond("t2", {"action": "skip_all"})
    for _ in range(6):                                          # 3 weak answers, each followed up
        view = coach.respond("t2", {"answer": "meh"})
    assert len(view["state"]["interview"]) == 6
    assert view["state"]["status"] == "finished"
    view = coach.respond("t2", {"action": "finish"})
    assert view["done"]
    try:
        coach.respond("t2", {"answer": "x"})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_skip_interview_question():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    coach.start("t8", _state())
    view = coach.respond("t8", {"action": "skip_all"})
    assert view["waiting_for"]["type"] == "interview_question"
    view = coach.respond("t8", {"action": "skip"})
    # Skipped: no follow-up, straight on to question 2, scored as unanswered.
    assert view["waiting_for"]["turn"] == 2 and not view["waiting_for"]["is_follow_up"]
    skipped = view["state"]["interview"][0]
    assert skipped["answer"] == "SKIPPED" and skipped["feedback"] == "Question skipped."
    assert skipped["score"] == {"correctness": 1, "depth": 1, "communication": 1}


    # A skip is no evidence of skill: it must not lift a skill above its resume level.
    view = coach.respond("t8", {"action": "end"})
    sk = next(s for s in view["state"]["skills"] if s["skill"] == skipped["skill"])
    obs = [o for o in sk["observations"] if o["source"] == "interview"]
    assert obs and all(o["value"] == 0.0 for o in obs) and sk["level"] <= sk["baseline"]


def test_end_interview_early():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    coach.start("t9", _state())
    coach.respond("t9", {"action": "skip_all"})
    view = coach.respond("t9", {"answer": "good answer"})
    assert view["waiting_for"]["turn"] == 2
    view = coach.respond("t9", {"action": "end"})
    # Wrapped up: only the answered question counts, the unanswered one is dropped.
    assert view["state"]["status"] in ("ready", "finished")
    assert [t["answer"] for t in view["state"]["interview"]] == ["good answer"]
    assert len(view["state"]["history"]) == 1 and view["state"]["summary"]


def test_end_interview_before_any_answer():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    coach.start("t10", _state())
    coach.respond("t10", {"action": "skip_all"})
    view = coach.respond("t10", {"action": "end"})
    assert view["state"]["interview"] == [] and view["state"]["status"] in ("ready", "finished")
    assert len(view["state"]["history"]) == 1


def test_quiz_text_literal_newlines_are_unescaped():
    from src.langgraphagenticai.coach.nodes import _unescape
    raw = "Given:\\n\\ndef f(x):\\n    return x"
    assert _unescape(raw) == "Given:\n\ndef f(x):\n    return x"
    assert _unescape("plain question") == "plain question"
    assert _unescape("sort 10\\,000\\,000 integers") == "sort 10,000,000 integers"


def test_scoring_is_deterministic_and_capped():
    sk = SkillLevel(skill="X", required_level=4, jd_weight=1, baseline=1, level=1)
    assert scoring.skill_level(sk, 0) == 1
    sk.observations.append(Observation(source="interview", value=scoring.interview_observation(5, 2), cycle=0))
    assert scoring.interview_observation(5, 2) == 3  # easy question can't prove expertise
    sk.level = scoring.skill_level(sk, 0)
    assert sk.level == round(0.3 * 1 + 0.7 * 3, 2)
    assert scoring.readiness([sk]) == round(100 * sk.level / 4, 1)


def test_role_profile_skips_jd_extraction_and_maps_names():
    llm = FakeLLM()
    coach = CoachGraph(CoachNodes(llm))
    role = [RoleSkill(skill="Python", required_level=3, jd_weight=1.0),
            RoleSkill(skill="Docker", required_level=3, jd_weight=0.8),
            RoleSkill(skill="SQL", required_level=3, jd_weight=0.6)]
    view = coach.start("t3", CoachState(candidate_id="c1", resume_text="r", role_skills=role,
                                        target_role="Python Backend Developer", interview_turns=2))
    assert "_JDProfile" not in llm.calls
    skills = {s["skill"]: s for s in view["state"]["skills"]}
    assert list(skills) == ["Python", "Docker", "SQL"]          # role's names, not the model's
    assert skills["Python"]["baseline"] == 3 and skills["Python"]["evidence"] == ["Built Flask APIs"]
    assert skills["Docker"]["baseline"] == 0                     # omitted by model -> no evidence
    assert view["state"]["target_role"] == "Python Backend Developer"


def test_role_store_seeds_once(tmp_path):
    db = str(tmp_path / "r.db")
    RoleStore(db)
    store = RoleStore(db)
    assert [r.slug for r in store.list()] == sorted([r.slug for r in SEED_ROLES], key=lambda s: store.get(s).title)
    assert store.get("python-backend").skills[0].skill == "Python"
    assert store.get("nope") is None


class FakeSearch:
    def __init__(self):
        self.calls = []

    def topic(self, query, official_site=""):
        self.calls.append(("topic", query, official_site))
        slug = query.replace(" ", "-")
        return [{"title": f"{query} doc", "url": f"https://ex.com/{slug}/0", "type": "docs"},
                {"title": f"{query} video", "url": f"https://youtube.com/watch?v={slug}", "type": "video", "meta": "12 min"}]

    def skill(self, skill, github_query, language=""):
        self.calls.append(("skill", skill, github_query, language))
        return [{"title": f"{skill} course", "url": f"https://www.coursera.org/learn/{skill}", "type": "course"},
                {"title": f"{skill}/repo", "url": f"https://github.com/x/{skill}", "type": "github", "meta": "★ 5K"}]


def test_plan_sources_curated_only_from_search_results():
    search = FakeSearch()
    coach = CoachGraph(CoachNodes(FakeLLM(), search=search))
    view = coach.start("t4", _state(target_readiness=85))
    plan = view["state"]["plan"]
    assert [p["skill"] for p in plan] == ["Docker", "SQL"]          # priority order, real names
    assert view["state"]["checkpoint_queue"] == ["Docker", "SQL"]

    docker, sql = plan
    assert [r["type"] for r in docker["resources"]] == ["github", "course"]   # curator's order
    images, compose = docker["topics"]
    assert [r["type"] for r in images["resources"]] == ["video", "docs"]
    assert images["resources"][0]["meta"] == "12 min"
    assert compose["resources"] == []                               # cross-topic pick rejected
    assert sql["topics"][0]["resources"] == []                      # curator found nothing good
    # SQL's skill-level key was not returned by the curator: fall back to
    # the first course and first repo from search.
    assert [r["type"] for r in sql["resources"]] == ["course", "github"]

    assert ("topic", "Docker images tutorial", "docs.docker.com") in search.calls
    assert ("skill", "Docker", "", "") in search.calls
    view = coach.respond("t4", {"action": "assess", "skill": "Docker"})
    assert view["waiting_for"]["topics"][0]["title"] == "Images"


def test_refresh_plan_keeps_pending_step():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    coach.start("t5", _state(target_readiness=85))
    before = coach.respond("t5", {"action": "assess", "skill": "Docker"})
    cfg = coach._cfg("t5")
    # Simulate a session saved in the old weekly format: skills, no topics.
    coach.graph.update_state(cfg, {"plan": [{"skill": "Docker"}, {"skill": "SQL"}]})
    assert all(not p["topics"] for p in coach.view("t5")["state"]["plan"])

    after = coach.refresh_plan("t5")
    assert [len(p["topics"]) for p in after["state"]["plan"]] == [2, 1]
    assert after["waiting_for"] == before["waiting_for"]       # same quiz still pending
    view = coach.respond("t5", {"answers": [0] * 10})       # and it still resumes
    assert view["waiting_for"]["pending"] == ["SQL"]


def test_clean_title_fixes_search_engine_junk():
    from src.langgraphagenticai.coach.search import clean_title
    glued = ("Tracing the Path in DFS, BFS, and Dijkstra’s Algorithm Graph Algorithms: BFS, DFS and Dijkstra "
             "Traced Step by Step ... Understanding Graph Traversals: BFS and DFS – AlgoCademy Blog ... DSA Graphs")
    cleaned = clean_title(glued)
    assert cleaned.startswith("Tracing the Path in DFS") and "AlgoCademy" not in cleaned and len(cleaned) <= 110
    assert clean_title("Python Asynchronous Programming - AsyncIO & Async/Await - YouTube") ==         "Python Asynchronous Programming - AsyncIO & Async/Await"
    assert clean_title("1.8.1 Asymptotic Notations Big Oh - Omega - Theta #1 - YouTube") ==         "1.8.1 Asymptotic Notations Big Oh - Omega - Theta #1"
    assert clean_title("Dynamic Programming or DP - GeeksforGeeks") == "Dynamic Programming or DP"
    assert clean_title("investopedia.com/terms/h/hypothesistesting.asp",
                       "https://www.investopedia.com/terms/h/hypothesistesting.asp") == "Hypothesistesting"
    assert len(clean_title("x " * 100)) <= 110


def test_fallback_never_shows_untrusted_links():
    """When the curator is unavailable, only vetted sources may be shown."""
    class SpamSearch(FakeSearch):
        def topic(self, query, official_site=""):
            return [{"title": "spam", "url": "https://psv4.vkuserphoto.ru/x", "type": "article"},
                    {"title": "doc", "url": "https://docs.docker.com/get-started/", "type": "docs"}]

    class NoCurator(FakeLLM):
        def respond(self, schema, prompt):
            if schema is N._Curation:
                raise RuntimeError("curator down")
            return super().respond(schema, prompt)

    coach = CoachGraph(CoachNodes(NoCurator(), search=SpamSearch()))
    plan = coach.start("t6", _state(target_readiness=85))["state"]["plan"]
    urls = [r["url"] for p in plan for t in p["topics"] for r in t["resources"]]
    assert urls and all("vkuserphoto" not in u for u in urls)
    assert all(u == "https://docs.docker.com/get-started/" for u in urls)


def test_switch_assessment_order_then_resume_queue():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    coach.start("t7", _state(target_readiness=85))
    view = coach.respond("t7", {"action": "assess", "skill": "Docker"})
    assert view["waiting_for"]["skill"] == "Docker" and view["waiting_for"]["pending"] == ["Docker", "SQL"]

    view = coach.respond("t7", {"action": "switch", "skill": "SQL"})   # SQL's topics were finished first
    assert view["waiting_for"]["type"] == "checkpoint" and view["waiting_for"]["skill"] == "SQL"
    assert view["state"]["switch_to"] is None

    view = coach.respond("t7", {"answers": [0] * 10})              # pass SQL
    assert view["waiting_for"]["pending"] == ["Docker"]                # back to studying the rest
    assert [c["skill"] for c in view["state"]["checkpoints"]] == ["SQL"]

    view = coach.respond("t7", {"action": "assess", "skill": "Nope"})  # unknown skill: ignored, still studying
    assert view["waiting_for"]["type"] == "study"
    view = coach.respond("t7", {"action": "skip_all"})
    assert view["waiting_for"]["type"] == "interview_question"


def test_topic_store_ticks_per_cycle(tmp_path):
    from src.langgraphagenticai.coach.store import TopicStore
    s = TopicStore(str(tmp_path / "t.db"))
    s.set("th", 0, "SQL", 1, True)
    s.set("th", 0, "SQL", 0, True)
    s.set("th", 0, "SQL", 0, True)          # idempotent
    s.set("th", 0, "Docker", 2, True)
    s.set("th", 0, "Docker", 2, False)
    s.set("th", 1, "SQL", 3, True)          # next cycle is separate
    assert s.done("th", 0) == {"SQL": [0, 1]}
    assert s.done("th", 1) == {"SQL": [3]}


def test_topic_tick_endpoint(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import coach_api

    coach_api.SourceSearch = lambda: None   # no network in tests
    app = FastAPI()
    app.include_router(coach_api.build_coach_router(FakeLLM(), str(tmp_path / "c.db")))
    client = TestClient(app)
    # (Newer FastAPI no longer lists included routes in app.routes; the calls below exercise the endpoint.)
    view = client.post("/coach/start", data={"candidate_id": "c", "jd_text": "x" * 60},
                       files={"resume": ("r.pdf", _tiny_pdf(), "application/pdf")}).json()
    tid = view["thread_id"]
    assert view["topic_done"] == {}
    r = client.post(f"/coach/{tid}/topics", json={"skill": "Docker", "topic_index": 1, "done": True}).json()
    assert r == {"topic_done": {"Docker": [1]}}
    assert client.get(f"/coach/{tid}").json()["topic_done"] == {"Docker": [1]}
    assert client.post(f"/coach/{tid}/topics", json={"skill": "Docker", "topic_index": 9, "done": True}).status_code == 422


def test_start_does_not_block_health(tmp_path, monkeypatch):
    """Starting a session runs LLM calls for a minute. It must not block the
    event loop: Render kills the instance when /health stops answering."""
    import asyncio
    import time as _time
    import httpx
    from fastapi import FastAPI
    import coach_api

    coach_api.SourceSearch = lambda: None   # no network in tests
    times = {}

    def slow_start(self, tid, state):          # stands in for a minute of LLM calls
        times["started"] = _time.monotonic()
        _time.sleep(1.5)
        times["ended"] = _time.monotonic()
        return {"thread_id": tid, "state": {"cycle": 0}}

    monkeypatch.setattr(CoachGraph, "start", slow_start)
    app = FastAPI()
    app.include_router(coach_api.build_coach_router(FakeLLM(), str(tmp_path / "c.db")))

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
            start = asyncio.create_task(client.post(
                "/coach/start", data={"candidate_id": "c", "jd_text": "x" * 60},
                files={"resume": ("r.pdf", _tiny_pdf(), "application/pdf")}))
            while "started" not in times:               # wait until /start is in the slow part
                await asyncio.sleep(0.01)
            assert (await client.get("/health")).status_code == 200
            health_done = _time.monotonic()
            assert (await start).status_code == 200
            return health_done

    # /health answered while /start was still running, not after it.
    assert asyncio.run(run()) < times["ended"]


def _tiny_pdf() -> bytes:
    content = "BT /F1 11 Tf 50 750 Td (Python developer resume) Tj ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offs = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    x = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offs)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{x}\n%%EOF"
    return out.encode()


def test_switch_endpoint_rejects_unknown_skill(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import coach_api

    coach_api.SourceSearch = lambda: None
    app = FastAPI()
    app.include_router(coach_api.build_coach_router(FakeLLM(), str(tmp_path / "c.db")))
    client = TestClient(app)
    tid = client.post("/coach/start", data={"candidate_id": "c", "jd_text": "x" * 60},
                      files={"resume": ("r.pdf", _tiny_pdf(), "application/pdf")}).json()["thread_id"]
    assert client.post(f"/coach/{tid}/respond", json={"action": "assess", "skill": "Nope"}).status_code == 422
    assert client.get(f"/coach/{tid}").json()["waiting_for"]["type"] == "study"         # untouched
    assert client.post(f"/coach/{tid}/respond", json={"action": "assess", "skill": "SQL"}).json()["waiting_for"]["skill"] == "SQL"
    assert client.post(f"/coach/{tid}/respond", json={"action": "switch", "skill": "Nope"}).status_code == 422


def test_daily_quota_switches_to_fallback_model_without_waiting():
    import time as _time

    class OutOfQuota:
        calls = 0

        def with_structured_output(self, schema, **kw):
            outer = self

            class Chain:
                def invoke(self, prompt):
                    outer.calls += 1
                    raise RuntimeError("Error code: 429 - Rate limit reached on tokens per day (TPD): Limit 200000")
            return Chain()

    primary, backup = OutOfQuota(), FakeLLM()
    nodes = CoachNodes(primary, fallback_llm=backup)
    t = _time.time()
    out = nodes._ask(N._Summary, "summarise")
    assert out.summary == "summary"
    assert primary.calls == 1 and backup.calls == ["_Summary"]
    assert _time.time() - t < 1          # no backoff sleeps for a daily limit


def _search_with(tavily="", langsearch=""):
    from src.langgraphagenticai.coach.search import SourceSearch
    return SourceSearch(github_token="", tavily_key=tavily, langsearch_key=langsearch)


def test_keyed_providers_skipped_without_keys():
    s = _search_with()
    assert s._web_tavily("q", "", 5) == [] and s._web_langsearch("q", "", 5) == [] and s.web("q") == []
    assert s.providers["web"] == [] and _search_with(tavily="t").providers["web"] == ["tavily"]


def test_langsearch_circuit_breaker_stops_retrying_a_failing_provider(monkeypatch):
    import src.langgraphagenticai.coach.search as search_mod
    s = _search_with(langsearch="l")
    attempts = []

    def failing(*a, **k):
        attempts.append(1)
        raise RuntimeError("connection reset")
    monkeypatch.setattr(search_mod, "_http_json", failing)
    for _ in range(3):
        s._web_langsearch("q", "", 5)
    before = len(attempts)
    assert s._web_langsearch("q", "", 5) == [] and len(attempts) == before   # breaker open: no more attempts


def test_web_search_order_langsearch_then_tavily(monkeypatch):
    s = _search_with(tavily="t", langsearch="l")
    calls = []
    hit = lambda name: [{"title": f"{name} doc", "url": f"https://docs.python.org/{name}", "body": "x"}]
    monkeypatch.setattr(s, "_web_langsearch", lambda q, site, n: calls.append("langsearch") or hit("langsearch"))
    monkeypatch.setattr(s, "_web_tavily", lambda q, site, n: calls.append("tavily") or hit("tavily"))
    assert s.web("python typing")[0]["url"].endswith("/langsearch") and calls == ["langsearch"]   # tavily quota untouched

    calls.clear()
    monkeypatch.setattr(s, "_web_langsearch", lambda q, site, n: calls.append("langsearch") or [])
    assert s.web("python typing")[0]["url"].endswith("/tavily") and calls == ["langsearch", "tavily"]
    assert s.providers["web"] == ["langsearch", "tavily"] and s.providers["pages"] == ["langsearch", "tavily"]


def test_langsearch_request_and_response(monkeypatch):
    import src.langgraphagenticai.coach.search as search_mod
    sent = {}

    def fake_http(url, headers, body=None, timeout=15):
        sent.update(url=url, auth=headers["Authorization"], body=body)
        return {"code": 200, "data": {"webPages": {"value": [
            {"name": "SQL Interview Questions - GeeksforGeeks", "url": "https://www.geeksforgeeks.org/sql-iq/",
             "snippet": "short", "text": "full page text " * 50}]}}}
    monkeypatch.setattr(search_mod, "_http_json", fake_http)
    s = _search_with(langsearch="key123")

    pages = s.pages("SQL interview questions", ["geeksforgeeks.org"], n=3, text_chars=9000)
    assert sent["url"] == "https://api.langsearch.com/v1/web-search" and sent["auth"] == "Bearer key123"
    assert sent["body"]["includeDomains"] == ["geeksforgeeks.org"]
    assert sent["body"]["contents"] == {"text": {"maxCharacters": 9000}}
    assert pages[0]["title"] == "SQL Interview Questions" and pages[0]["text"].startswith("full page text")

    assert s._web_langsearch("q", "geeksforgeeks.org", 5)[0]["body"] == "short"   # snippet when no text asked
    assert "contents" not in sent["body"]

    monkeypatch.setattr(search_mod, "_http_json", lambda *a, **k: {"code": 401, "msg": "bad key"})
    assert s._web_langsearch("q", "", 5) == []                                   # API error -> next provider


def test_pages_fall_back_to_tavily(monkeypatch):
    s = _search_with(tavily="t", langsearch="l")
    monkeypatch.setattr(s, "_langsearch", lambda *a, **k: [])
    monkeypatch.setattr(s, "_pages_tavily", lambda q, d, n, c: [{"title": "T", "url": "https://www.interviewbit.com/x/", "body": "text"}])
    assert s.pages("q", ["interviewbit.com"])[0]["url"] == "https://www.interviewbit.com/x/"
    assert _search_with().pages("q", []) == []


def test_study_links_point_at_official_current_docs():
    from src.langgraphagenticai.coach.search import canonical_url
    assert canonical_url("https://developers.google.cn/machine-learning/crash-course/linear-regression") == \
        "https://developers.google.com/machine-learning/crash-course/linear-regression"
    assert canonical_url("https://docs.python.org/release/3.9.16/library/typing.html") == \
        "https://docs.python.org/3/library/typing.html"
    assert canonical_url("https://docs.python.org/3.8/library/asyncio.html") == "https://docs.python.org/3/library/asyncio.html"
    assert canonical_url("https://docs.python.org/3/library/asyncio.html") == "https://docs.python.org/3/library/asyncio.html"
    assert canonical_url("https://pandas.pydata.org/pandas-docs/version/2.0/user_guide/advanced.html") == \
        "https://pandas.pydata.org/docs/user_guide/advanced.html"
    assert canonical_url("https://scikit-learn.org/0.24/modules/svm.html") == "https://scikit-learn.org/stable/modules/svm.html"
    assert canonical_url("https://realpython.com/python-3-9/") == "https://realpython.com/python-3-9/"


def test_checkpointer_knows_session_types():
    from src.langgraphagenticai.coach.graph import _serde
    from src.langgraphagenticai.coach.state import QuizQuestion
    serde = _serde()
    assert serde is not None
    q = QuizQuestion(question="q", options=["a", "b", "c", "d"], answer_index=1)
    assert serde.loads_typed(serde.dumps_typed(q)) == q


class _Flaky:
    """Fails with the given errors in order, then answers."""

    def __init__(self, errors):
        self.errors, self.calls = list(errors), []

    def with_structured_output(self, schema, **kwargs):
        llm = self

        class Chain:
            def invoke(self, prompt):
                llm.calls.append((kwargs.get("method", "tool"), "single valid JSON object" in prompt))
                if llm.errors:
                    raise llm.errors.pop(0)
                return N._Summary(summary="ok", next_steps=[])
        return Chain()


def test_malformed_output_gets_one_more_json_try():
    llm = _Flaky([RuntimeError("Error code: 400 - json_validate_failed"),
                  RuntimeError("Error code: 400 - tool_use_failed: model did not call a tool")])
    assert CoachNodes(llm)._ask(N._Summary, "summarise").summary == "ok"
    assert llm.calls == [("json_mode", False), ("tool", False), ("json_mode", True)]   # third try has the reminder


def test_other_errors_do_not_get_the_extra_try():
    llm = _Flaky([RuntimeError("401 invalid api key"), RuntimeError("401 invalid api key")])
    try:
        CoachNodes(llm)._ask(N._Summary, "summarise")
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the error")
    assert len(llm.calls) == 2



def test_exhausted_primary_model_is_skipped_for_a_while(monkeypatch):
    class OutOfQuota:
        calls = 0

        def with_structured_output(self, schema, **kwargs):
            outer = self

            class Chain:
                def invoke(self, prompt):
                    outer.calls += 1
                    raise RuntimeError("Rate limit reached ... tokens per day (TPD): Limit 200000")
            return Chain()

    primary, backup = OutOfQuota(), FakeLLM()
    nodes = CoachNodes(primary, fallback_llm=backup)
    nodes._ask(N._Summary, "one")
    nodes._ask(N._Summary, "two")
    assert primary.calls == 1 and backup.calls == ["_Summary", "_Summary"]   # second call skipped the primary

    import src.langgraphagenticai.coach.nodes as nodes_mod
    later = nodes_mod.time.time() + nodes.PRIMARY_QUOTA_PAUSE + 1
    monkeypatch.setattr(nodes_mod.time, "time", lambda: later)
    nodes._ask(N._Summary, "three")
    assert primary.calls == 2                                                # tried again after the pause


def test_rate_limited_key_hands_over_to_the_next_without_waiting(monkeypatch):
    class Limited:
        def __init__(self, name, error=None):
            self.name, self.error, self.calls = name, error, 0

        def with_structured_output(self, schema, **kwargs):
            llm = self

            class Chain:
                def invoke(self, prompt):
                    llm.calls += 1
                    if llm.error:
                        raise Exception(llm.error)
                    return N._Summary(summary=llm.name, next_steps=[])
            return Chain()

    monkeypatch.setattr(N.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("must not wait")))
    key1 = Limited("key1", "Error code: 429 - rate limit reached for tokens per minute (TPM)")
    key2 = Limited("key2")
    nodes = CoachNodes(key1, fallback_llm=[key2])
    assert nodes._ask(N._Summary, "p").summary == "key2"
    assert nodes._ask(N._Summary, "p").summary == "key2" and key1.calls == 1   # key1 paused for a minute


def test_groq_keys_are_collected_in_order_without_duplicates(monkeypatch):
    from src.langgraphagenticai.LLMS import groqllm
    monkeypatch.setattr(groqllm, "load_dotenv", lambda: None)
    for k in [k for k in __import__("os").environ if k.startswith("GROQ_API_KEY")]:
        monkeypatch.delenv(k)
    monkeypatch.setenv("GROQ_API_KEY", "a")
    monkeypatch.setenv("GROQ_API_KEY_2", "c")
    monkeypatch.setenv("GROQ_API_KEY_1", "b")
    monkeypatch.setenv("GROQ_API_KEY_3", "a")
    assert groqllm.groq_api_keys() == ["a", "b", "c"]
