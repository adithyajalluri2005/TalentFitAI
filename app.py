import os
import shutil
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional

from src.langgraphagenticai.graph.graph_builder import GraphBuilder
from src.langgraphagenticai.state.state import CandidateState

# ---------------------------
# App Setup
# ---------------------------
app = FastAPI(
    title="Recruitment Assistant API",
    description="Backend for LangGraph-powered Talent Acquisition Assistant."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------
# Graph Builder
# ---------------------------
graph_builder = GraphBuilder(model_name="qwen/qwen3-32b")

# ---------------------------
# Utility
# ---------------------------
def save_resume(resume: UploadFile, thread_id: str) -> str:
    temp_path = f"temp_{thread_id}_{resume.filename}"
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(resume.file, buffer)
    return temp_path

# ---------------------------
# Pydantic Models
# ---------------------------
class StatePayload(BaseModel):
    state: dict
    thread_id: str

# ---------------------------
# Endpoints
# ---------------------------

@app.post("/resume-upload")
async def resume_upload(resume: UploadFile = File(...)):
    thread_id = str(uuid.uuid4())
    temp_path = save_resume(resume, thread_id)
    try:
        state = CandidateState(resume_file=temp_path)
        final_state = graph_builder.run_resume(state, thread_id=thread_id)
        return JSONResponse({
            "thread_id": thread_id,
            "resume_skills": final_state.candidate_skills,
            "state": final_state.model_dump()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/jd-upload")
async def jd_upload(payload: StatePayload):
    try:
        candidate_state = CandidateState(**payload.state)
        candidate_state.jd_text = payload.state.get("jd_text", "")
        final_state = graph_builder.run_jd(candidate_state, thread_id=payload.thread_id)
        return {
            "thread_id": payload.thread_id,
            "jd_skills": final_state.jd_skills,
            "state": final_state.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/match")
async def match_resume_jd(payload: StatePayload):
    try:
        candidate_state = CandidateState(**payload.state)
        final_state = graph_builder.run_match(candidate_state, thread_id=payload.thread_id)
        return {
            "thread_id": payload.thread_id,
            "match_score": final_state.match_score,
            "matched_skills": final_state.matched_skills,
            "missing_skills": final_state.missing_skills,
            "state": final_state.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/skill-gap")
async def skill_gap(payload: StatePayload):
    try:
        candidate_state = CandidateState(**payload.state)
        final_state = graph_builder.run_skill_gap(candidate_state, thread_id=payload.thread_id)
        return {
            "thread_id": payload.thread_id,
            "missing_skills": final_state.missing_skills,
            "skill_resources": final_state.skill_resources,
            "state": final_state.model_dump()
        }
    except Exception as e:
        # Log the full error for debugging
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Skill gap error: {e}")



@app.post("/assessment")
async def generate_assessment(payload: StatePayload):
    try:
        candidate_state = CandidateState(**payload.state)
        final_state = graph_builder.run_assessment(candidate_state, thread_id=payload.thread_id)
        return {
            "thread_id": payload.thread_id,
            "mcqs": [q.model_dump() for q in final_state.mcqs],
            "state": final_state.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/interview")
async def generate_interview(payload: StatePayload):
    try:
        candidate_state = CandidateState(**payload.state)
        final_state = graph_builder.run_interview(candidate_state, thread_id=payload.thread_id)
        return {
            "thread_id": payload.thread_id,
            "interview_questions": [q.model_dump() for q in final_state.interview_questions],
            "state": final_state.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@app.post("/evaluate-interview")
async def evaluate_interview(payload: StatePayload):
    try:
        candidate_state = CandidateState(**payload.state)
        candidate_state.candidate_answers = payload.state.get("candidate_answers", [])

        # Make sure candidate_answers is a list of strings
        if not isinstance(candidate_state.candidate_answers, list):
            raise HTTPException(status_code=400, detail="candidate_answers must be a list of strings")

        final_state = graph_builder.run_evaluation(candidate_state, thread_id=payload.thread_id)
        return {
            "thread_id": payload.thread_id,
            "interview_score": final_state.interview_score,
            "feedback": final_state.feedback,
            "state": final_state.model_dump()
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Interview evaluation error: {e}")

@app.get("/")
async def root():
    return {"message": "✅ Recruitment Assistant API is running"}
