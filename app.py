import os
import shutil
import uuid
import tempfile
from groq import Groq
from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from ultralytics import YOLO                         # YOLOv8 model
from PIL import Image                  
import cv2
import io  
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
# Database imports
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

from src.langgraphagenticai.graph.graph_builder import GraphBuilder
from src.langgraphagenticai.state.state import CandidateState # Assumed available
from src.langgraphagenticai.nodes.nodes import WebSearchChatbotNode
from src.langgraphagenticai.LLMS.groqllm import GroqLLM # Assuming this is the class used in the node
import sqlite3
from datetime import datetime
# ---------------------------
# Database Configuration (SQLite) - CORRECTED
# ---------------------------
# Use a standard relative path for sqlite3 functions
DB_FILE_PATH = "./jds.db"
# Use the full URI for SQLAlchemy
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_FILE_PATH}" 

# SQLAlchemy Setup
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ---------------------------
# Database Model (SQLAlchemy)
# ---------------------------
class DBJobDescription(Base):
    __tablename__ = "job_descriptions"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    text = Column(String)
    company = Column(String) # Required for JDItem/init_db consistency
    created_at = Column(String) # Required for JDItem/init_db consistency

# Initialize database (used by sqlite3 endpoints)
def init_db():
    # Use the simple file path for sqlite3.connect()
    conn = sqlite3.connect(DB_FILE_PATH) 
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_descriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            text TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# Create tables for both SQLAlchemy and sqlite3 consistency
Base.metadata.create_all(bind=engine)
init_db() 


# Dependency to get the database session (SQLAlchemy)
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------
# App Setup & Globals (Unchanged)
# ---------------------------
app = FastAPI(
    title="Recruitment Assistant API",
    description="Backend for LangGraph-powered Talent Acquisition Assistant with JD Admin."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph_builder = GraphBuilder(model_name="qwen/qwen3-32b") 
ACTIVE_SESSIONS: Dict[str, CandidateState] = {}

try:
    temp_llm_instance = GroqLLM(model_name="qwen/qwen3-32b")
    temp_node = WebSearchChatbotNode(llm=temp_llm_instance)
except Exception as e:
    print(f"Warning: Could not initialize temp_node for utility matching: {e}")
    temp_node = None


# ---------------------------
# Pydantic Models for API
# ---------------------------
class StatePayload(BaseModel):
    state: dict
    thread_id: str

# Pydantic models for admin endpoints
class JDCreate(BaseModel):
    title: str
    text: str

class JDItem(BaseModel):
    title: str
    company: str
    text: str


class JDResponse(JDCreate):
    id: int
    company: str
    created_at: str
    class Config:
        from_attributes = True

class JDSummary(BaseModel):
    id: int
    title: str

# ---------------------------
# Utility (Unchanged)
# ---------------------------
def save_resume(resume: UploadFile, thread_id: str) -> str:
    temp_path = f"temp_{thread_id}_{resume.filename}"
    resume.file.seek(0)
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(resume.file, buffer)
    return temp_path


# ---------------------------
# JD Admin Endpoints (Using sqlite3 for manual CRUD)
# ---------------------------

# ✅ Add a new JD
@app.post("/admin/jds", response_model=JDItem)
def add_jd(jd: JDItem):
    # Use the simple file path
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO job_descriptions (title, company, text, created_at)
        VALUES (?, ?, ?, ?)
    """, (jd.title, jd.company, jd.text, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    
    return {**jd.model_dump(), "id": new_id}


# ✅ Get all JDs
@app.get("/admin/jds", response_model=List[JDResponse])
def list_jds():
    # Use the simple file path
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, company, text, created_at FROM job_descriptions ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "title": row[1],
            "company": row[2],
            "text": row[3],
            "created_at": row[4]
        }
        for row in rows
    ]


# ✅ Delete JD by ID
@app.delete("/admin/jds/{jd_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_jd(jd_id: int):
    # Use the simple file path
    conn = sqlite3.connect(DB_FILE_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM job_descriptions WHERE id = ?", (jd_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="JD not found")

    cursor.execute("DELETE FROM job_descriptions WHERE id = ?", (jd_id,))
    conn.commit()
    conn.close()
    return {"message": f"JD with ID {jd_id} deleted successfully"}


# ---------------------------
# Core Recruitment Endpoints (Using SQLAlchemy)
# ---------------------------

@app.get("/jds", response_model=List[JDSummary])
async def get_jds(db: Session = Depends(get_db)):
    """Returns a list of available job descriptions (ID and Title) from SQLite."""
    # Uses SQLAlchemy Session
    jds = db.query(DBJobDescription).all()
    return [{"id": jd.id, "title": jd.title} for jd in jds]


@app.post("/match-all-jds")
async def match_all_jds(payload: StatePayload, db: Session = Depends(get_db)):
    """Matches the candidate's resume against all JDs in the database and selects the best one."""
    if temp_node is None:
        raise HTTPException(status_code=500, detail="Internal server error: Matching utility not initialized.")
         
    try:
        candidate_state = CandidateState(**payload.state)
        best_match_score = -1.0
        best_match_jd: DBJobDescription = None
        best_match_jd_state: CandidateState = None
        
        # Query all JDs from the database (SQLAlchemy Session)
        all_jds = db.query(DBJobDescription).all()

        if not all_jds:
            raise HTTPException(status_code=404, detail="No Job Descriptions available for matching in the database.")
             
        # Use the pre-instantiated temp_node for matching logic
        for jd in all_jds:
            temp_state = candidate_state.copy(deep=True) 
            temp_state.jd_text = jd.text
            
            temp_state = temp_node.jd_upload(temp_state)
            temp_state = temp_node.match_resume_with_jd(temp_state)
            
            if temp_state.match_score > best_match_score:
                best_match_score = temp_state.match_score
                best_match_jd = jd
                best_match_jd_state = temp_state

        if best_match_jd_state is None:
            raise HTTPException(status_code=500, detail="Matching process failed to select a JD.")
             
        final_state = best_match_jd_state
        ACTIVE_SESSIONS[payload.thread_id] = final_state
        print("✅ Best Match JD ->", best_match_jd.title, best_match_jd.company, best_match_jd.created_at)
        return {
            "thread_id": payload.thread_id,
            "best_match_title": best_match_jd.title,
            "match_score": final_state.match_score,
            "jd_text": best_match_jd.text,
            "matched_skills": final_state.matched_skills,
            "missing_skills": final_state.missing_skills,
            "company": getattr(best_match_jd, "company", None) or getattr(best_match_jd, "company_name", None),
            "date": getattr(best_match_jd, "date", None) or getattr(best_match_jd, "created_at", None),
            "state": final_state.model_dump()
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Matching failed: {str(e)}")


# ---------------------------
# Unchanged Endpoints
# ---------------------------
@app.post("/resume-upload")
async def resume_upload(resume: UploadFile = File(...)):
    thread_id = str(uuid.uuid4())
    temp_path = save_resume(resume, thread_id)
    try:
        state = CandidateState(resume_file=temp_path)
        final_state = graph_builder.run_resume(state, thread_id=thread_id)
        
        ACTIVE_SESSIONS[thread_id] = final_state

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
    # Endpoint kept for compatibility, uses graph_builder.run_jd
    try:
        candidate_state = CandidateState(**payload.state)
        candidate_state.jd_text = payload.state.get("jd_text", "")
        final_state = graph_builder.run_jd(candidate_state, thread_id=payload.thread_id)
        
        ACTIVE_SESSIONS[payload.thread_id] = final_state
        
        return {
            "thread_id": payload.thread_id,
            "jd_skills": final_state.jd_skills,
            "state": final_state.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/match")
async def match_resume_jd(payload: StatePayload):
    # Endpoint kept for compatibility, uses graph_builder.run_match
    try:
        candidate_state = CandidateState(**payload.state)
        final_state = graph_builder.run_match(candidate_state, thread_id=payload.thread_id)

        ACTIVE_SESSIONS[payload.thread_id] = final_state
        
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
        
        ACTIVE_SESSIONS[payload.thread_id] = final_state
        
        return {
            "thread_id": payload.thread_id,
            "missing_skills": final_state.missing_skills,
            "skill_resources": final_state.skill_resources,
            "state": final_state.model_dump()
        }
    except Exception as e:
        import traceback
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Skill gap error: {e}")

@app.post("/assessment")
async def generate_assessment(payload: StatePayload):
    try:
        candidate_state = CandidateState(**payload.state)
        final_state = graph_builder.run_assessment(candidate_state, thread_id=payload.thread_id)

        ACTIVE_SESSIONS[payload.thread_id] = final_state
        
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

        ACTIVE_SESSIONS[payload.thread_id] = final_state
        
        return {
            "thread_id": payload.thread_id,
            "interview_questions": [q.model_dump() for q in final_state.interview_questions],
            "state": final_state.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transcribe-groq")
async def transcribe_groq(
    thread_id: str = Form(...),
    question_index: int = Form(...),
    file: UploadFile = File(...)
):
    """
    Transcribe uploaded audio using Groq Whisper and store text in session memory.
    """
    temp_path = None
    try:
        # Initialize Groq client
        if not os.getenv("GROQ_API_KEY"):
            raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured in environment.")
            
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        # 1. Retrieve current session from memory
        session_state = ACTIVE_SESSIONS.get(thread_id)
        if not session_state:
            raise HTTPException(status_code=404, detail=f"Session not found for thread_id: {thread_id}.")
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
            temp_path = tmp.name
            content = await file.read()
            if not content:
                raise ValueError("Uploaded file content is empty (zero bytes).")
            tmp.write(content)

        with open(temp_path, "rb") as audio_file:
            transcription_obj = client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-large-v3",
                response_format="text",
                language="en"
            )

        text = str(transcription_obj).strip()
        print(f"🧠 Transcribed (Q{question_index + 1}): {text[:100]}...")

        if not hasattr(session_state, "audio_transcripts"):
             session_state.audio_transcripts = {}

        session_state.audio_transcripts[int(question_index)] = text
        ACTIVE_SESSIONS[thread_id] = session_state

        return {"status": "success", "text": text}

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
        
        error_detail = str(e)
        if 'BadRequestError' in str(type(e)):
            error_detail = f"Groq API Error (Code 400): {e.response.json().get('error', {}).get('message', 'Check file format/API Key')}"
            raise HTTPException(status_code=400, detail=f"Transcription failed: {error_detail}")
            
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {error_detail}")


@app.post("/evaluate-interview")
async def evaluate_interview(payload: StatePayload):
    """
    Evaluate interview answers using the LLM.
    Returns per-question textual feedback only.
    """
    try:
        candidate_state = CandidateState(**payload.state)
        evaluated_state = graph_builder.run_evaluation(candidate_state, thread_id=payload.thread_id)
        ACTIVE_SESSIONS[payload.thread_id] = evaluated_state

        return {
            "status": "success",
            "thread_id": payload.thread_id,
            "feedback": evaluated_state.feedback,  
            "state": evaluated_state.model_dump(),
        }

    except Exception as e:
        print(f"❌ Evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Evaluation failed: {e}")

@app.get("/")
async def root():
    return {"message": "✅ Recruitment Assistant API is running"}