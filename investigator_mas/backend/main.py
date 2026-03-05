"""
backend/main.py
===============
FastAPI application entry point.

Run (from project root — the investigator_MAS/ folder):
    uvicorn backend.main:app --reload --port 8000

Swagger UI : http://localhost:8000/docs
ReDoc      : http://localhost:8000/redoc
Health     : http://localhost:8000/health
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.database import init_db
from backend.routers import auth, sow, applications

# from backend.routers.applications import router as applications_router
from dotenv import load_dotenv

# 1. LOAD THE .ENV FILE FIRST
# This makes sure os.environ is populated before anything else happens.
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB init once at startup — idempotent, safe to call on every restart."""
    init_db()
    yield


app = FastAPI(
    title="Investigator MAS — Permit Portal API",
    description=(
        "Austin DSD building permit application backend.\n\n"
        "**Powered by:** CrewAI × NVIDIA NIM (SOW + review crews) "
        "and Gemma 3 27B IT for blueprint visual reasoning."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
# Allows Streamlit dev server (:8501) and any future React/Angular (:3000) to call the API.
# Lock down allow_origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to ["https://your-domain.com"] in prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(applications.router)
app.include_router(sow.router)
# app.include_router(review.router)


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "service": "Investigator MAS Permit Portal API v1.0"}
