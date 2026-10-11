"""Drives the whole coaching loop through every interrupt with a scripted LLM."""
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
        if schema is N._Quiz:
            return N._Quiz(questions=[QuizQuestion(question=f"q{i}", options=["a", "b", "c", "d"], answer_index=0) for i in range(4)])
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


def test_full_loop_reaches_ready_and_records_history():
    snapshots = []
    coach = CoachGraph(CoachNodes(FakeLLM(), on_snapshot=lambda s, t, snap: snapshots.append((t, snap))))

    view = coach.start("t1", _state(target_readiness=85))
    # Diagnosis done, two gap skills -> first checkpoint, answers hidden from client.
    assert view["waiting_for"]["type"] == "checkpoint"
    assert view["waiting_for"]["skill"] == "Docker"  # highest weight x gap
    assert "answer_index" not in str(view["waiting_for"])
    assert "current_quiz" not in view["state"]
    start_readiness = view["readiness"]

    view = coach.respond("t1", {"answers": [0, 0, 0, 0]})       # Docker: perfect
    assert view["waiting_for"]["skill"] == "SQL"
    assert view["readiness"] > start_readiness                 # live score moves on checkpoint
    view = coach.respond("t1", {"action": "skip"})              # SQL: skipped
    assert view["waiting_for"]["type"] == "interview_question"

    # Cycle 0: weak answers -> follow-up, ends below target, so loop re-plans.
    view = coach.respond("t1", {"answer": "meh"})
    assert view["waiting_for"]["is_follow_up"] is True
    view = coach.respond("t1", {"answer": "meh"})
    view = coach.respond("t1", {"answer": "meh"})
    assert view["state"]["cycle"] == 1
    assert view["state"]["status"] == "learning"
    assert len(view["state"]["history"]) == 1
    assert view["waiting_for"]["type"] == "checkpoint"          # new cycle, new plan

    view = coach.respond("t1", {"action": "skip_all"})
    for _ in range(3):
        view = coach.respond("t1", {"answer": "good answer"})

    assert view["done"] is True
    assert view["state"]["status"] == "ready"
    h = view["state"]["history"]
    assert len(h) == 2 and h[1]["readiness"] > h[0]["readiness"]
    assert [t for t, _ in snapshots] == ["t1", "t1"]


def test_respond_when_not_waiting_raises():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    st = _state(max_cycles=1)
    coach.start("t2", st)
    coach.respond("t2", {"action": "skip_all"})
    for _ in range(3):
        view = coach.respond("t2", {"answer": "meh"})
    assert view["done"] and view["state"]["status"] == "finished"
    try:
        coach.respond("t2", {"answer": "x"})
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


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
    assert view["waiting_for"]["topics"][0]["title"] == "Images"


def test_refresh_plan_keeps_pending_step():
    coach = CoachGraph(CoachNodes(FakeLLM()))
    before = coach.start("t5", _state(target_readiness=85))
    cfg = coach._cfg("t5")
    # Simulate a session saved in the old weekly format: skills, no topics.
    coach.graph.update_state(cfg, {"plan": [{"skill": "Docker"}, {"skill": "SQL"}]})
    assert all(not p["topics"] for p in coach.view("t5")["state"]["plan"])

    after = coach.refresh_plan("t5")
    assert [len(p["topics"]) for p in after["state"]["plan"]] == [2, 1]
    assert after["waiting_for"] == before["waiting_for"]       # same quiz still pending
    view = coach.respond("t5", {"answers": [0, 0, 0, 0]})       # and it still resumes
    assert view["waiting_for"]["skill"] == "SQL"


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
    view = coach.start("t7", _state(target_readiness=85))
    assert view["waiting_for"]["skill"] == "Docker" and view["waiting_for"]["pending"] == ["Docker", "SQL"]

    view = coach.respond("t7", {"action": "switch", "skill": "SQL"})   # SQL's topics were finished first
    assert view["waiting_for"]["type"] == "checkpoint" and view["waiting_for"]["skill"] == "SQL"
    assert view["state"]["switch_to"] is None

    view = coach.respond("t7", {"answers": [0, 0, 0, 0]})              # pass SQL
    assert view["waiting_for"]["skill"] == "Docker"                    # back to the remaining skill
    assert [c["skill"] for c in view["state"]["checkpoints"]] == ["SQL"]

    view = coach.respond("t7", {"action": "switch", "skill": "Nope"})  # unknown skill: ignored, treated as no answers
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
    router_coach = [r for r in app.routes if getattr(r, "path", "") == "/coach/{thread_id}/topics"]
    assert router_coach
    # build a session directly through the graph the router uses
    view = client.post("/coach/start", data={"candidate_id": "c", "jd_text": "x" * 60},
                       files={"resume": ("r.pdf", _tiny_pdf(), "application/pdf")}).json()
    tid = view["thread_id"]
    assert view["topic_done"] == {}
    r = client.post(f"/coach/{tid}/topics", json={"skill": "Docker", "topic_index": 1, "done": True}).json()
    assert r == {"topic_done": {"Docker": [1]}}
    assert client.get(f"/coach/{tid}").json()["topic_done"] == {"Docker": [1]}
    assert client.post(f"/coach/{tid}/topics", json={"skill": "Docker", "topic_index": 9, "done": True}).status_code == 422


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
    assert client.post(f"/coach/{tid}/respond", json={"action": "switch", "skill": "Nope"}).status_code == 422
    assert client.get(f"/coach/{tid}").json()["waiting_for"]["skill"] == "Docker"     # untouched
    assert client.post(f"/coach/{tid}/respond", json={"action": "switch", "skill": "SQL"}).json()["waiting_for"]["skill"] == "SQL"


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
