from typing import Optional, Any
import uuid

from langgraph.graph import StateGraph, START, END
try:
    from langgraph.checkpoint.memory import MemorySaver
except Exception:
    MemorySaver = None

from src.langgraphagenticai.state.state import CandidateState
from src.langgraphagenticai.LLMS.groqllm import GroqLLM
from src.langgraphagenticai.nodes.nodes import WebSearchChatbotNode


class GraphBuilder:
    """
    Builds independent graphs (single-node) for each step:
      - resume_graph
      - jd_graph
      - match_graph
      - skill_gap_graph
      - assessment_graph
      - interview_graph

    Also builds a full_workflow_graph chaining all steps.
    Each graph is compiled with CandidateState as the state model.
    Helper run_* methods accept CandidateState or plain dict and return CandidateState.
    """

    def __init__(self, model_name: str = "deepseek-r1-distill-llama-70b"):
        self.llm = GroqLLM(model_name=model_name)
        self.recruitment_node = WebSearchChatbotNode(self.llm)

        # optional persistent checkpointer
        self.checkpointer = MemorySaver() if MemorySaver is not None else None

        # compile individual single-node graphs
        self.resume_graph = self._single_node_graph("resume_upload", self.recruitment_node.resume_upload)
        self.jd_graph = self._single_node_graph("jd_upload", self.recruitment_node.jd_upload)
        self.match_graph = self._single_node_graph("match_resume_with_jd", self.recruitment_node.match_resume_with_jd)
        self.skill_gap_graph = self._single_node_graph("skill_gap_analysis", self.recruitment_node.skill_gap_analysis)
        self.assessment_graph = self._single_node_graph("generate_assessment", self.recruitment_node.generate_assessment)
        self.interview_graph = self._single_node_graph("generate_interview_questions", self.recruitment_node.generate_interview_questions)
        self.evaluation_graph = self._single_node_graph("evaluate_candidate", self.recruitment_node.evaluate_answers)

        # full workflow graph
        self.full_workflow_graph = self._build_full_graph()

    # ---------------- helpers ---------------- #
    def _single_node_graph(self, name: str, fn) -> Any:
        g = StateGraph(CandidateState)
        g.add_node(name, fn)
        g.add_edge(START, name)
        g.add_edge(name, END)
        if self.checkpointer is not None:
            return g.compile(checkpointer=self.checkpointer)
        return g.compile()

    def _build_full_graph(self) -> Any:
        g = StateGraph(CandidateState)

        g.add_node("resume_upload", self.recruitment_node.resume_upload)
        g.add_node("jd_upload", self.recruitment_node.jd_upload)
        g.add_node("match_resume_with_jd", self.recruitment_node.match_resume_with_jd)
        g.add_node("skill_gap_analysis", self.recruitment_node.skill_gap_analysis)
        g.add_node("generate_assessment", self.recruitment_node.generate_assessment)
        g.add_node("generate_interview_questions", self.recruitment_node.generate_interview_questions)

        g.add_edge(START, "resume_upload")
        g.add_edge("resume_upload", "jd_upload")
        g.add_edge("jd_upload", "match_resume_with_jd")
        g.add_edge("match_resume_with_jd", "skill_gap_analysis")
        g.add_edge("skill_gap_analysis", "generate_assessment")
        g.add_edge("generate_assessment", "generate_interview_questions")
        g.add_edge("generate_interview_questions", END)

        if self.checkpointer is not None:
            return g.compile(checkpointer=self.checkpointer)
        return g.compile()

    # ---------------- runtime helpers ---------------- #
    def _cfg(self, thread_id: Optional[str]):
        if not thread_id:
            return None
        return {"configurable": {"thread_id": thread_id}}

    def _to_candidate_state(self, result: Any) -> CandidateState:
        if isinstance(result, CandidateState):
            return result
        try:
            if hasattr(result, "model_dump"):
                return CandidateState(**result.model_dump())
        except Exception:
            pass
        if isinstance(result, dict):
            return CandidateState(**result)
        try:
            return CandidateState(**dict(result))
        except Exception as e:
            raise ValueError(f"Could not convert graph result to CandidateState: {e}")

    # ---------------- run methods ---------------- #
    def run_resume(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.resume_graph.invoke(state, config=cfg) if cfg else self.resume_graph.invoke(state)
        return self._to_candidate_state(res)

    def run_jd(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.jd_graph.invoke(state, config=cfg) if cfg else self.jd_graph.invoke(state)
        return self._to_candidate_state(res)

    def run_match(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.match_graph.invoke(state, config=cfg) if cfg else self.match_graph.invoke(state)
        return self._to_candidate_state(res)

    def run_skill_gap(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.skill_gap_graph.invoke(state, config=cfg) if cfg else self.skill_gap_graph.invoke(state)
        return self._to_candidate_state(res)

    def run_assessment(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.assessment_graph.invoke(state, config=cfg) if cfg else self.assessment_graph.invoke(state)
        return self._to_candidate_state(res)

    def run_interview(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.interview_graph.invoke(state, config=cfg) if cfg else self.interview_graph.invoke(state)
        return self._to_candidate_state(res)
    
    def run_evaluation(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.evaluation_graph.invoke(state, config=cfg) if cfg else self.evaluation_graph.invoke(state)
        return self._to_candidate_state(res)

    def run_full(self, state: CandidateState | dict, thread_id: Optional[str] = None) -> CandidateState:
        if isinstance(state, dict):
            state = CandidateState(**state)
        cfg = self._cfg(thread_id)
        res = self.full_workflow_graph.invoke(state, config=cfg) if cfg else self.full_workflow_graph.invoke(state)
        return self._to_candidate_state(res)
