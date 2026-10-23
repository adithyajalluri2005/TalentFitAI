"""Sourced questions: selection, and how web questions seed the interview and make up assessments."""
import re

from src.langgraphagenticai.coach import nodes as N
from src.langgraphagenticai.coach import questions as Q
from src.langgraphagenticai.coach.nodes import CoachNodes
from src.langgraphagenticai.coach.questions import SourcedMCQ, SourcedQuestion, pick_quiz, pick_seeds, skill_matches
from src.langgraphagenticai.coach.state import CoachState, InterviewTurn, RubricScore, SkillLevel


def _q(id, difficulty, skill="SQL"):
    return SourcedQuestion(id=id, skill=skill, difficulty=difficulty, question=f"question {id}?",
                           key_points=[f"{id} a", f"{id} b"], source_name="GeeksforGeeks",
                           source_url=f"https://www.geeksforgeeks.org/{id}/")


QUESTIONS = [_q(f"sql-{d}", d) for d in range(1, 6)] + [_q("py-1", 1, skill="Python")]


class FakeWeb:
    """Stands in for WebQuestions: fixed questions, no search."""

    def __init__(self, questions=(), mcqs=()):
        self.questions, self.mcqs = list(questions), list(mcqs)

        self.prefetched = []

    def harvest(self, skill, ask, wait=None):
        return self.questions, self.mcqs

    def prefetch(self, skills, ask):
        self.prefetched += skills


class RecordingLLM:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def with_structured_output(self, schema, **kwargs):
        llm = self

        class Chain:
            def invoke(self, prompt):
                llm.prompts.append(prompt)
                return llm.reply(schema, prompt)
        return Chain()


def _state(**kw):
    return CoachState(candidate_id="c", resume_text="r", target_role="Backend Dev", interview_turns=3,
                      skills=[SkillLevel(skill="SQL", required_level=3, jd_weight=1.0, level=2)], **kw)


def test_skill_matching_allows_a_qualifier_but_not_a_different_skill():
    assert skill_matches("SQL", "sql")
    assert skill_matches("SQL", "SQL (PostgreSQL)")
    assert skill_matches("Python", "Python 3")
    assert skill_matches("Data Structures & Algorithms", "Data Structures and Algorithms")
    assert not skill_matches("Python", "Scripting (Bash/Python)")
    assert not skill_matches("Python", "Pandas & NumPy")


def test_seeds_closest_difficulty_first_and_skip_used():
    assert [q.id for q in pick_seeds(QUESTIONS, "SQL (PostgreSQL)", 3)] == ["sql-3", "sql-4", "sql-2"]
    assert [q.id for q in pick_seeds(QUESTIONS, "SQL", 3, used_ids=["sql-3", "sql-4"])] == ["sql-2", "sql-5", "sql-1"]
    assert pick_seeds(QUESTIONS, "Kubernetes", 3) == []


def test_ids_are_stable():
    assert Q.question_id("web-iq", "SQL", "Find the  SECOND highest salary?") == \
        Q.question_id("web-iq", "sql", "find the second highest salary?")
    assert Q.question_id("web-iq", "SQL (PostgreSQL)", "x").startswith("web-iq-sql_postgresql-")


def test_interview_asks_from_seed_and_grades_against_its_key_points():
    llm = RecordingLLM(lambda schema, p: N._Question(question="adapted", seed=1) if schema is N._Question else
                       N._Evaluation(score=RubricScore(correctness=3, depth=3, communication=3), feedback="f", needs_follow_up=False))
    nodes = CoachNodes(llm, web_questions=FakeWeb(QUESTIONS))
    state = _state()

    turn = nodes.interview_ask(state)["interview"][-1]
    assert "SEED QUESTIONS" in llm.prompts[-1] and "[0] (difficulty 3) question sql-3?" in llm.prompts[-1]
    assert turn.bank_id == "sql-4" and turn.difficulty == 4          # seed 1 = next closest
    assert turn.key_points == ["sql-4 a", "sql-4 b"]
    assert turn.source_name == "GeeksforGeeks" and turn.source_url.endswith("/sql-4/")

    state = state.model_copy(update={"interview": [turn.model_copy(update={"answer": "my answer"})]})
    nodes.interview_eval(state)
    assert "REFERENCE KEY POINTS" in llm.prompts[-1] and "- sql-4 b" in llm.prompts[-1]

    # A used seed is not offered again.
    nodes.interview_ask(state)
    assert "sql-4?" not in llm.prompts[-1]


def test_without_web_questions_the_model_writes_key_points_and_no_source():
    llm = RecordingLLM(lambda schema, p: N._Question(question="q", key_points=["x", "y"]))
    turn = CoachNodes(llm, web_questions=FakeWeb()).interview_ask(_state())["interview"][-1]
    assert "SEED" not in llm.prompts[-1] and "key_points" in llm.prompts[-1]
    assert turn.bank_id == "" and turn.key_points == ["x", "y"] and turn.source_url == ""

    # A seed number out of range is ignored rather than trusted.
    llm = RecordingLLM(lambda schema, p: N._Question(question="q", seed=7, key_points=["m", "n"]))
    turn = CoachNodes(llm, web_questions=FakeWeb(QUESTIONS)).interview_ask(_state())["interview"][-1]
    assert turn.bank_id == "" and turn.key_points == ["m", "n"] and turn.difficulty == 3


def test_eval_without_key_points_is_unchanged():
    llm = RecordingLLM(lambda schema, p: N._Evaluation(score=RubricScore(correctness=2, depth=2, communication=2), feedback="f", needs_follow_up=True))
    turn = InterviewTurn(skill="SQL", difficulty=2, question="q", answer="a")
    CoachNodes(llm).interview_eval(_state(interview=[turn]))
    assert "REFERENCE KEY POINTS" not in llm.prompts[-1]


def test_view_hides_key_points_until_answered():
    from src.langgraphagenticai.coach.graph import CoachGraph
    from test_coach_graph import FakeLLM, _state as graph_state

    coach = CoachGraph(CoachNodes(FakeLLM(), web_questions=FakeWeb(QUESTIONS)))
    coach.start("kp", graph_state())
    coach.respond("kp", {"action": "skip_all"})
    coach.graph.update_state(coach._cfg("kp"), {"interview": [
        InterviewTurn(skill="SQL", difficulty=2, question="q", key_points=["secret", "k2"])]})
    assert coach.view("kp")["state"]["interview"][-1]["key_points"] == []
    coach.graph.update_state(coach._cfg("kp"), {"interview": [
        InterviewTurn(skill="SQL", difficulty=2, question="q", answer="a", key_points=["secret", "k2"])]})
    assert coach.view("kp")["state"]["interview"][-1]["key_points"] == ["secret", "k2"]


# ---------------- assessments ---------------- #

def _mcq(id, difficulty=3, topic="", skill="SQL", options=("w", "x", "y", "z"), answer=0):
    return SourcedMCQ(id=id, skill=skill, topic=topic, difficulty=difficulty, question=f"mcq {id}?",
                      options=list(options), answer_index=answer, explanation=f"because {id}",
                      source_name="InterviewBit", source_url=f"https://www.interviewbit.com/{id}/")


def test_quiz_prefers_studied_topics_spreads_topics_and_takes_what_there_is():
    mcqs = [
        _mcq("j1", 3, "Joins"), _mcq("j2", 3, "Joins"), _mcq("j3", 2, "Joins"),
        _mcq("i1", 3, "Indexes"), _mcq("w1", 3, "Window functions"), _mcq("t1", 5, "Transactions"),
        _mcq("p1", 1, "Joins", skill="Python"),
    ]
    picked = [q.id for q in pick_quiz(mcqs, "SQL", 3, topics=["SQL joins in depth", "Window functions"], n=4)]
    assert picked == ["w1", "j1", "i1", "t1"]   # best topic match first, then one per topic
    assert [q.id for q in pick_quiz(mcqs, "SQL", 3, used_ids=["j1", "w1"], n=4)] == ["i1", "j2", "t1", "j3"]
    # Fewer left than asked for: all of them (the model writes the rest).
    assert [q.id for q in pick_quiz(mcqs, "SQL", 3, used_ids=["j1", "j2", "j3"], n=4)] == ["i1", "w1", "t1"]
    assert len(pick_quiz(mcqs, "SQL", 3)) == 6                     # default size is a full assessment (10)
    assert pick_quiz(mcqs, "Kubernetes", 3) == []


def test_shuffle_is_stable_and_keeps_the_answer_but_not_positional_options():
    q = _mcq("s1", options=("right", "w1", "w2", "w3"), answer=0)
    opts, ans = q.shuffled("cand|0")
    assert opts[ans] == "right" and sorted(opts) == sorted(q.options)
    assert q.shuffled("cand|0") == (opts, ans)
    assert {q.shuffled(f"c{i}")[1] for i in range(20)} != {0}      # not always first

    for positional in ("All of the above", "None of these options", "Both A and C", "A and B"):
        p = _mcq("s2", options=("one", "two", "three", positional), answer=3)
        assert p.shuffled("x") == (list(p.options), 3)
    assert not Q._POSITIONAL.search("data and code") and not Q._POSITIONAL.search("A list of tuples")


def _quiz_reply(schema, prompt, prefix):
    n = int(re.search(r"exactly (\d+) multiple-choice", prompt).group(1))
    return schema(questions=[N._QuizItem(question=f"{prefix}{i}", options=["a", "b", "c", "d"], answer_index=1)
                             for i in range(n)])


def test_checkpoint_uses_web_questions_and_model_fills_the_rest():
    from src.langgraphagenticai.coach.state import SkillTopics, Topic

    assert CoachNodes.QUIZ_SIZE == 10 and CoachNodes.QUIZ_MIN_WEB == 5
    web = FakeWeb(mcqs=[_mcq(f"m{i}", 3, f"T{i}", options=("right", "a", "b", "c")) for i in range(3)])
    llm = RecordingLLM(lambda schema, p: _quiz_reply(schema, p, "g"))
    nodes = CoachNodes(llm, web_questions=web)
    state = _state(checkpoint_queue=["SQL"], plan=[SkillTopics(skill="SQL", topics=[Topic(title="T2 stuff")])])

    out = nodes.make_checkpoint(state)
    quiz = out["current_quiz"]
    assert len(quiz) == 10 and quiz[0].bank_id == "m2"             # studied topic first
    web_part, model_part = quiz[:3], quiz[3:]
    assert all(q.options[q.answer_index] == "right" and q.source_url for q in web_part)
    assert [q.question for q in model_part] == [f"g{i}" for i in range(7)] and all(q.source_url == "" for q in model_part)
    # Too few web questions: the model writes the missing 7 and is told not to repeat the web ones.
    assert "exactly 7 multiple-choice" in llm.prompts[-1] and "mcq m2?" in llm.prompts[-1]
    assert "This is a retake" not in llm.prompts[-1]

    answers = [q.answer_index for q in quiz[:9]] + [(quiz[9].answer_index + 1) % 4]
    graded = nodes.grade_checkpoint(state.model_copy(update={**out, "quiz_answers": answers}))
    result = graded["checkpoints"][-1]
    assert result.score == 0.9 and len(result.review) == 10
    assert result.review[9].chosen != result.review[9].answer_index
    assert result.review[0].source_name == "InterviewBit" and result.review[0].explanation == "because m2"

    # A retake skips web questions already used; none left -> the model writes all 10, avoiding the earlier ones.
    nodes.llm = RecordingLLM(lambda schema, p: _quiz_reply(schema, p, "r"))
    again = nodes.make_checkpoint(state.model_copy(update={"checkpoints": [result]}))["current_quiz"]
    assert [q.question for q in again] == [f"r{i}" for i in range(10)]
    assert all(q.source_url == "" for q in again)
    assert "exactly 10 multiple-choice" in nodes.llm.prompts[-1]
    assert "This is a retake" in nodes.llm.prompts[-1] and "mcq m2?" in nodes.llm.prompts[-1]


def test_enough_web_questions_make_a_sourced_only_quiz():
    llm = RecordingLLM(lambda schema, p: (_ for _ in ()).throw(AssertionError("model must not write the quiz")))
    for n, size in ((6, 6), (12, 10)):
        web = FakeWeb(mcqs=[_mcq(f"m{i}", 3, f"T{i}") for i in range(n)])
        quiz = CoachNodes(llm, web_questions=web).make_checkpoint(_state(checkpoint_queue=["SQL"]))["current_quiz"]
        assert len(quiz) == size and all(q.source_url for q in quiz)


def test_short_model_quiz_is_rejected_not_shrunk():
    schema = N._quiz_schema(4)
    item = N._QuizItem(question="q", options=["a", "b", "c", "d"], answer_index=0)
    for bad in (3, 7):
        try:
            schema(questions=[item] * bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad} questions accepted for a 4-question quiz")
    assert len(schema(questions=[item] * 5).questions) == 5        # a small overshoot is trimmed by the caller


def test_too_easy_seed_is_raised_keeping_its_source():
    llm = RecordingLLM(lambda schema, p: N._Question(question="harder version", seed=0, key_points=["k1", "k2", "k3"]))
    state = CoachState(candidate_id="c", resume_text="r", target_role="Dev", interview_turns=3,   # needs difficulty 5
                       skills=[SkillLevel(skill="SQL", required_level=5, jd_weight=1.0, level=4)])
    turn = CoachNodes(llm, web_questions=FakeWeb([_q("sql-1", 1), _q("sql-2", 2)])).interview_ask(state)["interview"][-1]
    assert "raise it to 5" in llm.prompts[-1]
    assert turn.bank_id == "sql-2" and turn.difficulty == 5 and turn.key_points == ["k1", "k2", "k3"]
    assert turn.source_url.endswith("/sql-2/")                               # concept page still linked


def test_resume_rated_once_per_skill_and_reused():
    from src.langgraphagenticai.coach.state import RoleSkill
    calls = []

    def reply(schema, prompt):
        calls.append(prompt)
        names = [n for n in ("Python", "SQL", "Docker") if f"'{n}'" in prompt]
        return N._ResumeRatings(ratings=[N._ResumeRating(skill=n, resume_level=3) for n in names])
    nodes = CoachNodes(RecordingLLM(reply))
    rs = lambda *names: [RoleSkill(skill=n, required_level=3, jd_weight=1.0) for n in names]

    nodes.rate_resume("my resume", rs("Python", "SQL"))
    again = nodes.rate_resume("my resume", rs("SQL", "Python", "Docker"))     # only Docker is new
    assert len(calls) == 2 and "'Docker'" in calls[1] and "'Python'" not in calls[1]
    assert {s.skill: s.baseline for s in again} == {"SQL": 3, "Python": 3, "Docker": 3}
    nodes.rate_resume("another resume", rs("Python"))
    assert len(calls) == 3                                                    # different resume: rated fresh


def _three_skill_state(**kw):
    return CoachState(candidate_id="c", resume_text="r", target_role="Dev", interview_turns=4, skills=[
        SkillLevel(skill="Docker", required_level=3, jd_weight=0.8, level=1),
        SkillLevel(skill="SQL", required_level=3, jd_weight=0.6, level=1),
        SkillLevel(skill="Python", required_level=3, jd_weight=1.0, level=3),   # no gap
    ], **kw)


def test_plan_starts_question_retrieval_for_its_skills():
    from test_coach_graph import FakeLLM
    web = FakeWeb()
    nodes = CoachNodes(FakeLLM(), web_questions=web)
    plan = nodes.plan(_three_skill_state())["plan"]
    assert [p.skill for p in plan] == ["Docker", "SQL"]
    assert web.prefetched == ["Docker", "SQL"]              # priority order, while the candidate studies


def test_interview_start_retrieves_questions_for_its_skills():
    from test_coach_graph import FakeLLM
    web = FakeWeb()
    nodes = CoachNodes(FakeLLM(), web_questions=web)
    state = _three_skill_state()
    out = nodes.interview_ask(state)
    assert web.prefetched == ["Docker", "SQL"]               # only skills the interview will ask about
    # Later questions do not start retrieval again.
    web.prefetched = []
    nodes.interview_ask(state.model_copy(update=out))
    assert web.prefetched == []
