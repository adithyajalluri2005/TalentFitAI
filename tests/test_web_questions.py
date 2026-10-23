"""Web question retrieval: page text, evidence check, caching, and use by the coach."""
from src.langgraphagenticai.coach import nodes as N
from src.langgraphagenticai.coach import web_questions as W
from src.langgraphagenticai.coach.nodes import CoachNodes
from src.langgraphagenticai.coach.state import CoachState, SkillLevel

PAGE = ("A primary key uniquely identifies each row in a table and cannot be NULL. "
        "A LEFT JOIN returns all rows from the left table and the matched rows from the right table. "
        "An index speeds up reads on a column but slows down inserts and updates. ") * 8
GFG = "https://www.geeksforgeeks.org/sql-interview-questions/"
IB = "https://www.interviewbit.com/sql-interview-questions/"


class FakeSearch:
    def __init__(self, hits=None):
        self.calls = []
        self.hits = hits if hits is not None else {"geeksforgeeks.org": [{"url": GFG}], "interviewbit.com": [{"url": IB}]}

    def web(self, query, site="", n=6):
        self.calls.append((query, site))
        return self.hits.get(site, [])


def extraction(schema, prompt):
    assert schema in (W._WebInterviewSet, W._WebMCQSet, W._MCQChecks) and PAGE[:40] in prompt
    if schema is W._MCQChecks:   # the independent re-answer agrees with every key
        return W._MCQChecks(checks=[W._MCQCheck(index=i, answer_index=0, unambiguous=True) for i in range(3)])
    if schema is W._WebMCQSet:
        return W._WebMCQSet(mcqs=_mcqs(prompt))
    return W._WebInterviewSet(
        interview=[
            W._WebInterviewQ(question="What is a primary key?", difficulty=1, key_points=["unique per row", "not NULL"],
                             evidence="A primary key uniquely identifies each row in a table"),
            W._WebInterviewQ(question="Invented question?", difficulty=2, key_points=["a", "b"],
                             evidence="This sentence is nowhere on the page at all"),
        ])


def _mcqs(prompt):
    return [W._WebMCQ(question=f"Which join keeps unmatched left rows ({i}, {'gfg' if GFG in prompt else 'ib'})?",
                        topic="Joins", difficulty=2,
                        options=["LEFT JOIN", "INNER JOIN", "CROSS JOIN", "SELF JOIN"], answer_index=0,
                        explanation="It keeps every left row.",
                        evidence="a left join returns all rows from the LEFT table, and the matched rows")
            for i in range(3)]


def _web(tmp_path, search=None, fetch=lambda url: PAGE):
    return W.WebQuestions(search or FakeSearch(), str(tmp_path / "w.db"), fetch=fetch)


def test_html_to_text_prefers_article_and_drops_chrome():
    html = ("<html><head><style>x{}</style><script>var a=1</script></head><body><nav>Menu Login</nav>"
            "<article><h1>SQL Questions</h1><p>" + "Joins combine rows. " * 80 + "</p></article>"
            "<footer>Copyright</footer></body></html>")
    p = W._TextExtractor()
    p.feed(html)
    text = p.text()
    assert text.startswith("SQL Questions\nJoins combine rows.")
    assert "Menu" not in text and "var a" not in text and "Copyright" not in text


def test_evidence_must_really_be_on_the_page():
    page = W._norm(PAGE)
    assert W.on_page("a LEFT join returns all rows -- from the left table", page)
    assert not W.on_page("primary key", page)                        # too short to prove anything
    assert not W.on_page("A RIGHT JOIN returns all rows from the right table", page)


def test_harvest_keeps_verified_questions_links_them_and_caches(tmp_path):
    search = FakeSearch()
    web = _web(tmp_path, search)
    asks = []
    questions, mcqs = web.harvest("SQL", lambda s, p: asks.append(1) or extraction(s, p))

    assert len(asks) == 6                                            # interview + quiz + quiz check per page
    # Unverified "Invented question?" dropped; the same question on both sites kept once.
    assert [q.question for q in questions] == ["What is a primary key?"]
    assert questions[0].source_name == "GeeksforGeeks" and questions[0].source_url == GFG
    assert len(mcqs) == 6 and {q.source_url for q in mcqs} == {GFG, IB}

    # Second call (even from a new instance, e.g. after a restart) comes from SQLite.
    again = _web(tmp_path, search).harvest("sql", lambda s, p: (_ for _ in ()).throw(AssertionError("cached")))
    assert [q.id for q in again[1]] == [q.id for q in mcqs]
    assert len(search.calls) == 2


def test_harvest_never_raises_and_does_not_cache_a_search_outage(tmp_path):
    web = _web(tmp_path, FakeSearch(hits={}))
    assert web.harvest("SQL", extraction) == ([], [])
    assert web._cached("SQL") is None                                # search found nothing: retry next time

    def boom(url):
        raise OSError("blocked")
    web = _web(tmp_path, fetch=boom)
    assert web.harvest("SQL", extraction) == ([], [])
    assert web._cached("SQL") == ([], [])                            # pages were unreachable: short negative cache

    web = W.WebQuestions(FakeSearch(), str(tmp_path / "other.db"), fetch=lambda u: PAGE)
    assert web.harvest("SQL", lambda s, p: (_ for _ in ()).throw(RuntimeError("LLM down"))) == ([], [])


def test_prefetch_warms_cache_in_background(tmp_path):
    web = _web(tmp_path)
    web.prefetch(["SQL"], extraction)
    web._pool.shutdown(wait=True)
    assert web._cached("SQL") is not None
    assert web.harvest("SQL", lambda s, p: (_ for _ in ()).throw(AssertionError("cached")))[1]


def _state(**kw):
    return CoachState(candidate_id="c", resume_text="r", target_role="Backend Dev", interview_turns=3,
                      skills=[SkillLevel(skill="SQL", required_level=2, jd_weight=1.0, level=1)], **kw)


def test_coach_uses_web_questions_with_sources(tmp_path):
    web = _web(tmp_path)
    web.harvest("SQL", extraction)                                   # warm cache

    def llm_reply(schema, prompt):
        if schema is N._Question:
            assert "What is a primary key?" in prompt
            return N._Question(question="What is a primary key?", seed=0)
        if issubclass(schema, N._Quiz):
            return _quiz_reply(schema, prompt, "g")
        raise AssertionError(f"model must not write {schema.__name__}")

    from test_questions import RecordingLLM, _quiz_reply
    nodes = CoachNodes(RecordingLLM(llm_reply), web_questions=web)

    quiz = nodes.make_checkpoint(_state(checkpoint_queue=["SQL"]))["current_quiz"]
    # The two pages give 6 verified questions: enough for a quiz of sourced questions only.
    assert len(quiz) == 6 and all(q.source_url in (GFG, IB) for q in quiz)

    nodes.INTRO_TURN, nodes.RESUME_TURNS = None, ()          # straight to a skill question
    turn = nodes.interview_ask(_state())["interview"][-1]
    assert turn.source_url in (GFG, IB) and turn.key_points == ["unique per row", "not NULL"]


def test_page_text_from_search_api_skips_fetching(tmp_path):
    class PagesSearch(FakeSearch):
        def pages(self, query, domains, n=3, text_chars=9000, keep=None):
            assert domains == list(W.QUESTION_SITES)
            return keep([{"url": GFG, "text": PAGE}, {"url": GFG + "2", "text": PAGE}, {"url": IB, "text": PAGE}])

    def no_fetch(url):
        raise AssertionError("page text came with the search result")
    search = PagesSearch()
    questions, mcqs = _web(tmp_path, search, fetch=no_fetch).harvest("SQL", extraction)
    assert {q.source_url for q in mcqs} == {GFG, IB}                 # one page per site first
    assert search.calls == []                                        # plain web search not needed


def test_only_interview_pages_naming_the_skill_first():
    hits = [{"url": "https://www.geeksforgeeks.org/courses/master-python", "title": "Python course interview prep"},
            {"url": "https://www.interviewbit.com/ci-cd-interview-questions", "title": "CI/CD Interview Questions"},
            {"url": "https://www.geeksforgeeks.org/devops/docker-interview-questions", "title": "Docker Interview Questions"},
            {"url": "https://www.geeksforgeeks.org/what-is-docker", "title": "What is Docker"},
            {"url": "https://www.interviewbit.com/blog/kubernetes-vs-docker", "title": "Kubernetes vs Docker - InterviewBit"}]
    assert [h["url"].rsplit("/", 1)[-1] for h in W._relevant(hits, "Docker")] == \
        ["docker-interview-questions"]
    r_page = [{"url": "https://www.interviewbit.com/r-interview-questions/", "title": "R Interview Questions"}]
    assert W._relevant(r_page, "Statistics & Probability") == []          # does not name the skill



def test_quiz_check_drops_disputed_and_ambiguous_questions(tmp_path):
    def reply(schema, prompt):
        if schema is W._MCQChecks:
            return W._MCQChecks(checks=[
                W._MCQCheck(index=0, answer_index=0, unambiguous=True),    # agrees: kept
                W._MCQCheck(index=1, answer_index=2, unambiguous=True),    # different answer: dropped
                W._MCQCheck(index=2, answer_index=0, unambiguous=False),   # ambiguous: dropped
            ])
        return extraction(schema, prompt)
    web = _web(tmp_path, FakeSearch(hits={"geeksforgeeks.org": [{"url": GFG}]}))
    _, mcqs = web.harvest("SQL", reply)
    assert [q.question.split("(")[1][0] for q in mcqs] == ["0"]


def test_failed_extraction_is_retried_after_an_hour_not_a_day(tmp_path, monkeypatch):
    def quiz_call_fails(schema, prompt):
        if schema is W._WebMCQSet:
            raise RuntimeError("json_validate_failed")
        return extraction(schema, prompt)
    web = _web(tmp_path, FakeSearch(hits={"geeksforgeeks.org": [{"url": GFG}]}))
    questions, mcqs = web.harvest("SQL", quiz_call_fails)
    assert questions and mcqs == []

    now = W.time.time()
    monkeypatch.setattr(W.time, "time", lambda: now + 2 * 3600)          # two hours later
    assert web._cached("SQL") is None                                   # incomplete: retry
    web._save("SQL", questions, [], complete=True)
    assert web._cached("SQL") is not None                               # complete: kept for 30 days



def test_harvest_waits_only_as_long_as_asked(tmp_path):
    import threading
    gate = threading.Event()

    def slow(schema, prompt):
        gate.wait(5)
        return extraction(schema, prompt)
    web = _web(tmp_path, FakeSearch(hits={"geeksforgeeks.org": [{"url": GFG}]}))
    t = W.time.time()
    assert web.harvest("SQL", slow, wait=0) == ([], [])            # interview: cache only, never blocks
    assert web.harvest("SQL", slow, wait=0.2) == ([], [])          # quiz: bounded wait
    assert W.time.time() - t < 2
    gate.set()
    web._pool.shutdown(wait=True)                                  # retrieval finished in the background
    assert web._cached("SQL")[1]


def test_refers_to_source_drops_page_dependent_questions():
    from src.langgraphagenticai.coach.web_questions import refers_to_source
    # Real questions the generator produced: unanswerable without the page.
    assert refers_to_source("Which graph traversal algorithm is mentioned first in the page?")
    assert refers_to_source("Which of the following is an example of a non-linear data structure as described?")
    assert refers_to_source("According to the article, which index type is fastest?")
    assert refers_to_source("How does the page define a queue?")
    assert refers_to_source("What does the article recommend for indexing?")
    assert refers_to_source("In the page's example, which key is evicted first?")
    # Ordinary questions, including OS ones about pages, are kept.
    assert not refers_to_source("Which data structure follows the Last-In-First-Out (LIFO) principle?")
    assert not refers_to_source("What happens on a page fault, and how does the page table help?")
    assert not refers_to_source("Describe the LRU page replacement algorithm.")
    assert not refers_to_source("What is the time complexity of merging k sorted arrays with a heap?")


def test_topic_name_drops_bracketed_qualifiers():
    from src.langgraphagenticai.coach.web_questions import topic_name
    assert topic_name("Deep Learning (PyTorch/TensorFlow)") == "Deep Learning"
    assert topic_name("Testing (pytest)") == "pytest"            # "Testing" alone is too vague
    assert topic_name("Django or FastAPI/Flask") == "Django or FastAPI/Flask"
    assert topic_name("SQL") == "SQL"
