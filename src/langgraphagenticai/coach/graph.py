"""The coaching loop as a single cyclic LangGraph.

    diagnose -> plan -> [make_checkpoint -> await_checkpoint* -> grade_checkpoint]... ->
    [interview_ask -> await_answer* -> interview_eval]... -> critic -> rescore -> summarize
    -> END (ready / out of cycles) | plan (next cycle)

    * pauses the graph with interrupt(); resume with Command(resume=<reply>).
"""
import logging
import sqlite3
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.langgraphagenticai.coach import scoring
from src.langgraphagenticai.coach.nodes import CoachNodes
from src.langgraphagenticai.coach.state import CoachState

logger = logging.getLogger(__name__)


def make_checkpointer(db_path: Optional[str]):
    """SQLite-backed so a coaching session survives restarts (sessions span
    days); falls back to memory if the sqlite saver is not installed."""
    if db_path:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
            return SqliteSaver(sqlite3.connect(db_path, check_same_thread=False))
        except ImportError:
            logger.warning("langgraph-checkpoint-sqlite not installed; coaching sessions will not survive restarts")
    return MemorySaver()


class CoachGraph:
    def __init__(self, nodes: CoachNodes, checkpointer=None):
        self.nodes = nodes
        self.graph = self._build().compile(checkpointer=checkpointer or MemorySaver())

    def _build(self) -> StateGraph:
        n = self.nodes
        g = StateGraph(CoachState)
        g.add_node("diagnose", n.diagnose)
        g.add_node("plan", n.plan)
        g.add_node("make_checkpoint", n.make_checkpoint)
        g.add_node("await_checkpoint", n.await_checkpoint)
        g.add_node("grade_checkpoint", n.grade_checkpoint)
        g.add_node("interview_ask", n.interview_ask)
        g.add_node("await_answer", n.await_answer)
        g.add_node("interview_eval", n.interview_eval)
        g.add_node("critic", n.critic)
        g.add_node("rescore", n.rescore)
        g.add_node("summarize", n.summarize)

        g.add_edge(START, "diagnose")
        g.add_edge("diagnose", "plan")
        learning = {"make_checkpoint": "make_checkpoint", "interview_ask": "interview_ask"}
        g.add_conditional_edges("plan", n.route_learning, learning)
        g.add_edge("make_checkpoint", "await_checkpoint")
        g.add_conditional_edges("await_checkpoint", n.route_after_await,
                                {"make_checkpoint": "make_checkpoint", "grade_checkpoint": "grade_checkpoint"})
        g.add_conditional_edges("grade_checkpoint", n.route_learning, learning)
        g.add_edge("interview_ask", "await_answer")
        g.add_edge("await_answer", "interview_eval")
        g.add_conditional_edges("interview_eval", n.route_interview,
                                {"interview_ask": "interview_ask", "critic": "critic"})
        g.add_edge("critic", "rescore")
        g.add_edge("rescore", "summarize")
        g.add_conditional_edges("summarize", n.route_after_cycle, {"plan": "plan", "end": END})
        return g

    # ---------------- runtime ---------------- #

    @staticmethod
    def _cfg(thread_id: str) -> dict:
        # Each interview turn is ~3 supersteps and checkpoints ~3 per skill;
        # the default limit of 25 would stop a long session mid-cycle.
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": 200}

    def start(self, thread_id: str, state: CoachState) -> dict:
        self.graph.invoke(state, config=self._cfg(thread_id))
        return self.view(thread_id)

    def respond(self, thread_id: str, reply: Any) -> dict:
        snap = self.graph.get_state(self._cfg(thread_id))
        if not snap.next:
            raise ValueError("Session is not waiting for input.")
        self.graph.invoke(Command(resume=reply), config=self._cfg(thread_id))
        return self.view(thread_id)

    def refresh_plan(self, thread_id: str) -> dict:
        """Rebuild the study topics in place (e.g. a session saved in an older
        plan format). Only `plan` changes: without `as_node`, LangGraph treats
        the update as coming from the last node that ran, so the pending quiz or
        interview question is kept."""
        cfg = self._cfg(thread_id)
        state = CoachState.model_validate(self.graph.get_state(cfg).values)
        self.graph.update_state(cfg, {"plan": self.nodes.plan(state)["plan"]})
        # The update clears the stored interrupt; re-run the pending await_*
        # node (it has no side effects) so it asks the same question again.
        if self.graph.get_state(cfg).next:
            self.graph.invoke(None, config=cfg)
        return self.view(thread_id)

    def view(self, thread_id: str) -> Optional[dict]:
        """Client-safe view of a session: state plus whatever the graph is
        waiting for. Quiz answers are stripped so they cannot be read early."""
        snap = self.graph.get_state(self._cfg(thread_id))
        if not snap.values:
            return None
        state = CoachState.model_validate(snap.values)
        pending = next((t.interrupts[0].value for t in snap.tasks if t.interrupts), None)
        return {
            "thread_id": thread_id,
            "waiting_for": pending,
            "done": not snap.next,
            # Live estimate (moves with checkpoints); history holds the official re-scores.
            "readiness": scoring.readiness(state.skills),
            "state": state.model_dump(exclude={"current_quiz", "resume_text", "jd_text"}),
        }
