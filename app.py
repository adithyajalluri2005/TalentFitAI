import os
import shutil
import sqlite3
import time
from datetime import datetime

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from coach_api import build_coach_router
from src.langgraphagenticai.LLMS.groqllm import GroqLLM

load_dotenv()

# ---------------------------
# Database
# ---------------------------
# DB_PATH lets the host point this at a persistent disk (e.g. /var/data/jds.db on
# Render); falls back to the repo-local file for local development.
DB_FILE_PATH = os.getenv("DB_PATH", "./jds.db")
os.makedirs(os.path.dirname(os.path.abspath(DB_FILE_PATH)), exist_ok=True)

# On a fresh persistent disk, seed from the copy committed to the repo.
if not os.path.exists(DB_FILE_PATH) and os.path.exists("./jds.db"):
    shutil.copyfile("./jds.db", DB_FILE_PATH)

# ---------------------------
# App
# ---------------------------
app = FastAPI(
    title="TalentFitAI Career Coach API",
    description="LangGraph coaching loop: diagnose -> plan -> checkpoints -> mock interview -> re-score.",
)

# Comma-separated list of allowed origins, e.g.
# "https://talentfitai.vercel.app,http://localhost:8080". Defaults to open.
# An empty/whitespace value falls back to "*" rather than an empty list, which
# would reject every origin and surface as an opaque CORS failure in the browser.
CORS_ORIGINS = [
    o.strip()
    for o in ((os.getenv("CORS_ORIGINS") or "").strip() or "*").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Groq retires models periodically (llama-3.3-70b-versatile and qwen/qwen3-32b
# are both gone), so the model id is configurable without a code change.
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Has its own daily quota on Groq; takes over when GROQ_MODEL's runs out.
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")

# Monotonic so /health uptime is immune to wall-clock jumps.
PROCESS_START = time.monotonic()

app.include_router(build_coach_router(
    GroqLLM(model_name=GROQ_MODEL).llm, DB_FILE_PATH,
    fallback_llm=GroqLLM(model_name=GROQ_FALLBACK_MODEL).llm if GROQ_FALLBACK_MODEL else None,
))


@app.get("/")
async def root():
    return {"message": "✅ TalentFitAI Career Coach API is running"}


# ---------------------------
# Health Check
# ---------------------------
# Kept deliberately cheap: no LLM/network calls, just a DB round-trip, so the
# external keep-alive ping (.github/workflows/keep-alive.yml) costs nothing but
# still proves the process can serve real work. Render also uses this as its
# healthCheckPath.
@app.get("/health")
async def health():
    started = datetime.utcnow()
    db_error = None
    try:
        with sqlite3.connect(DB_FILE_PATH) as conn:
            conn.execute("SELECT 1")
    except Exception as e:
        db_error = str(e)

    payload = {
        "status": "ok" if not db_error else "degraded",
        "service": "talentfitai-api",
        "timestamp": started.isoformat() + "Z",
        "uptime_seconds": round(time.monotonic() - PROCESS_START, 1),
        "checks": {
            "database": "ok" if not db_error else "error",
            "llm_model": GROQ_MODEL,
            "llm_fallback_model": GROQ_FALLBACK_MODEL,
            "groq_key": "set" if os.getenv("GROQ_API_KEY") else "missing",
        },
    }
    if db_error:
        payload["checks"]["database_error"] = db_error

    # 503 on a bad DB so uptime monitors and Render's health check actually
    # register the failure instead of seeing a cheerful 200.
    return JSONResponse(status_code=200 if not db_error else 503, content=payload)
