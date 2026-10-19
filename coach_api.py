"""HTTP API for the candidate coaching loop.

Flow for a client:
    GET  /coach/roles                 -> role tracks to pick from
    POST /coach/suggest-roles         -> resume vs every track, ranked ("which role suits me?")
    POST /coach/start                 -> view (waiting_for = first checkpoint quiz or interview question)
    POST /coach/transcribe            -> spoken answer -> text + delivery metrics
    POST /coach/{thread_id}/respond   -> view (repeat until done)
    GET  /coach/{thread_id}           -> view (resume a session later, e.g. after a week of study)
    GET  /coach/progress/{candidate}  -> readiness history across all sessions
"""
import os
import re
import tempfile
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from pypdf import PdfReader

from src.langgraphagenticai.coach import scoring
from src.langgraphagenticai.coach.graph import CoachGraph, make_checkpointer
from src.langgraphagenticai.coach.nodes import CoachNodes
from src.langgraphagenticai.coach.roles import RoleStore
from src.langgraphagenticai.coach.search import SourceSearch
from src.langgraphagenticai.coach.web_questions import WebQuestions
from src.langgraphagenticai.coach.state import CoachState
from src.langgraphagenticai.coach.store import ProgressStore, TopicStore


FILLER_WORDS = re.compile(r"\b(um+|uh+|erm|hmm+|like|you know|basically|actually|i mean|sort of|kind of)\b", re.I)


class TopicTick(BaseModel):
    skill: str
    topic_index: int
    done: bool


class RespondPayload(BaseModel):
    answers: Optional[List[int]] = None         # checkpoint quiz
    action: Optional[str] = None                # "assess" | "retake" | "interview" | "skip" | "skip_all" | "switch"
    skill: Optional[str] = None                 # with "assess"/"retake"/"switch": the skill to assess
    answer: Optional[str] = None                # interview answer (typed or transcribed)
    voice_metrics: Optional[Dict[str, float]] = None


async def _resume_text(resume: UploadFile) -> str:
    fd, path = tempfile.mkstemp(suffix=".pdf")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(await resume.read())
        text = "\n".join((p.extract_text() or "") for p in PdfReader(path).pages)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Could not read the resume PDF: {e}")
    finally:
        os.remove(path)
    if not text.strip():
        raise HTTPException(status_code=422, detail="The resume PDF has no extractable text (is it a scanned image?)")
    return text


def build_coach_router(llm, db_path: str, fallback_llm=None) -> APIRouter:
    store = ProgressStore(db_path)
    topics = TopicStore(db_path)
    roles = RoleStore(db_path)
    search = SourceSearch()
    nodes = CoachNodes(
        llm,
        search=search,
        fallback_llm=fallback_llm,
        web_questions=WebQuestions(search, db_path) if search else None,
        on_snapshot=lambda state, thread_id, snap: store.record(state.candidate_id, thread_id, state.target_role, snap),
    )
    coach = CoachGraph(nodes, checkpointer=make_checkpointer(db_path))
    router = APIRouter(prefix="/coach", tags=["coach"])

    def with_topics(view: Optional[dict]) -> Optional[dict]:
        if view is not None:
            view["topic_done"] = topics.done(view["thread_id"], view["state"]["cycle"])
        return view

    @router.get("/roles")
    def list_roles():
        return roles.list()

    @router.post("/suggest-roles")
    async def suggest_roles(resume: UploadFile = File(...)):
        """Rate the resume once on the union of all tracks' skills, then score
        every track from those ratings. Same scoring as a coaching session."""
        text = await _resume_text(resume)
        tracks = roles.list()
        union = list({s.skill.lower(): s for r in tracks for s in r.skills}.values())
        try:
            rated = {s.skill.lower(): s for s in await run_in_threadpool(nodes.rate_resume, text, union)}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Resume rating failed: {e}")
        results = []
        for r in tracks:
            skills = []
            for rs in r.skills:
                s = rated[rs.skill.lower()].model_copy(update={"required_level": rs.required_level, "jd_weight": rs.jd_weight})
                skills.append(s)
            top_gaps = sorted(skills, key=scoring.priority, reverse=True)[:3]
            results.append({
                "slug": r.slug, "title": r.title, "description": r.description,
                "readiness": scoring.readiness(skills),
                "strengths": [s.skill for s in skills if s.gap == 0 and s.jd_weight >= 0.6],
                "top_gaps": [{"skill": s.skill, "level": s.level, "required_level": s.required_level}
                             for s in top_gaps if s.gap > 0],
            })
        return sorted(results, key=lambda x: x["readiness"], reverse=True)

    @router.post("/start")
    async def start(
        candidate_id: str = Form(...),
        resume: UploadFile = File(...),
        role_slug: Optional[str] = Form(None),
        jd_text: Optional[str] = Form(None),
        target_role: str = Form(""),
        target_readiness: float = Form(90),
    ):
        role = roles.get(role_slug) if role_slug else None
        if role_slug and not role:
            raise HTTPException(status_code=404, detail="Unknown role")
        if not role and not (jd_text or "").strip():
            raise HTTPException(status_code=422, detail="Pick a role or paste a job description")

        state = CoachState(
            candidate_id=candidate_id, resume_text=await _resume_text(resume),
            role_slug=role.slug if role else None,
            role_skills=role.skills if role else [],
            jd_text="" if role else jd_text,
            target_role=role.title if role else target_role,
            target_readiness=target_readiness,
        )
        thread_id = str(uuid.uuid4())
        try:
            # The graph makes LLM calls for a minute or more: run it off the event
            # loop so /health keeps answering (Render kills the instance otherwise).
            return with_topics(await run_in_threadpool(coach.start, thread_id, state))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Coaching session failed to start: {e}")

    @router.post("/transcribe")
    async def transcribe(file: UploadFile = File(...)):
        """Whisper transcription plus delivery metrics (pace, filler words),
        which the interview evaluator uses for the communication score."""
        from groq import Groq
        from src.langgraphagenticai.LLMS.groqllm import groq_api_keys
        keys = groq_api_keys()
        if not keys:
            raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")
        content = await file.read()
        if not content:
            raise HTTPException(status_code=422, detail="Empty recording")
        result, error = None, None
        for key in keys:  # next key when one is out of quota or rate limited
            try:
                result = await run_in_threadpool(
                    Groq(api_key=key).audio.transcriptions.create,
                    file=(file.filename or "answer.webm", content),
                    model="whisper-large-v3-turbo", response_format="verbose_json", language="en",
                )
                break
            except Exception as e:
                error = e
                if not any(s in str(e).lower() for s in ("429", "rate limit", "quota")):
                    break
        if result is None:
            raise HTTPException(status_code=502, detail=f"Transcription failed: {error}")
        text = (result.text or "").strip()
        duration = float(getattr(result, "duration", 0) or 0)
        words = len(text.split())
        return {
            "text": text,
            "voice_metrics": {
                "duration_seconds": round(duration, 1),
                "words_per_minute": round(words / (duration / 60), 1) if duration else 0.0,
                "filler_words": float(len(FILLER_WORDS.findall(text))),
            },
        }

    @router.get("/progress/{candidate_id}")
    def progress(candidate_id: str):
        return store.history(candidate_id)

    @router.post("/{thread_id}/respond")
    def respond(thread_id: str, payload: RespondPayload) -> Dict[str, Any]:
        current = coach.view(thread_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if payload.action in ("assess", "switch"):
            pending = (current["waiting_for"] or {}).get("pending", [])
            if payload.skill not in pending:
                raise HTTPException(status_code=422, detail=f"No assessment pending for {payload.skill!r}")
        if payload.action == "retake":
            if payload.skill not in (current["waiting_for"] or {}).get("retakeable", []):
                raise HTTPException(status_code=422, detail=f"No assessment to retake for {payload.skill!r}")
        try:
            return with_topics(coach.respond(thread_id, payload.model_dump(exclude_none=True)))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Coaching step failed: {e}")

    @router.post("/{thread_id}/refresh-plan")
    def refresh_plan(thread_id: str) -> Dict[str, Any]:
        view = coach.view(thread_id)
        if view is None:
            raise HTTPException(status_code=404, detail="Session not found")
        if view["done"]:
            raise HTTPException(status_code=409, detail="Session is finished")
        try:
            return with_topics(coach.refresh_plan(thread_id))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not rebuild study topics: {e}")

    @router.post("/{thread_id}/topics")
    def tick_topic(thread_id: str, tick: TopicTick) -> Dict[str, Any]:
        """Mark a study topic done/undone. Returns the ticked topics for the cycle."""
        view = coach.view(thread_id)
        if view is None:
            raise HTTPException(status_code=404, detail="Session not found")
        plan = {p["skill"]: p for p in view["state"]["plan"]}
        if tick.skill not in plan or not 0 <= tick.topic_index < len(plan[tick.skill]["topics"]):
            raise HTTPException(status_code=422, detail="Unknown skill or topic")
        cycle = view["state"]["cycle"]
        topics.set(thread_id, cycle, tick.skill, tick.topic_index, tick.done)
        return {"topic_done": topics.done(thread_id, cycle)}

    @router.get("/{thread_id}")
    def get_session(thread_id: str):
        view = coach.view(thread_id)
        if view is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return with_topics(view)

    return router
