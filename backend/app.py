"""
app.py – FastAPI application for the Verifiable Alpha Signals Marketplace.

Endpoints:
  POST /start-signal              → enqueue a new inference job
  GET  /signal-status/{job_id}    → poll job status + signal result
  GET  /fetch-proof/{job_id}      → retrieve proof metadata + URL
  GET  /proofs/{filename}         → serve locally stored proof files

Plugin-prefixed mirrors (for Claude plugin):
  POST /api/plugin/start-signal
  GET  /api/plugin/status/{job_id}
  GET  /api/plugin/fetch-proof/{job_id}
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import redis as redis_lib
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rq import Queue
from sqlalchemy.orm import Session

from db import get_db, init_db
from models import Job, Proof, Signal

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

REDIS_URL: str = os.environ["REDIS_URL"]
SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")
BACKEND_API_KEY: str = os.getenv("BACKEND_API_KEY", "change-me-backend-api-key")

app = FastAPI(
    title="Verifiable Alpha Signals Marketplace",
    version="1.0.0",
    description="Paid, verifiable trading signals powered by OpenGradient.",
)

# ── Redis / RQ setup ──────────────────────────────────────────────────────────
redis_conn = redis_lib.from_url(REDIS_URL)
signal_queue = Queue("signals", connection=redis_conn)

# ── Serve locally stored proofs ───────────────────────────────────────────────
PROOFS_DIR = Path(__file__).parent / "proofs"
PROOFS_DIR.mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def on_startup():
    init_db()
    logger.info("DB initialised")


# ── Auth dependency ───────────────────────────────────────────────────────────

def verify_api_key(request: Request):
    """Simple API-key gate (Bearer or X-API-Key header)."""
    auth = request.headers.get("Authorization", "")
    x_key = request.headers.get("X-API-Key", "")
    token = auth.removeprefix("Bearer ").strip() or x_key
    if token != BACKEND_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class StartSignalRequest(BaseModel):
    ticker: str = "BTC"
    timeframe: str = "1h"
    model_id: str | None = None
    extra_inputs: dict = {}


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    signal: dict | None = None
    error: str | None = None


class ProofResponse(BaseModel):
    job_id: str
    proof_hash: str | None = None
    storage_url: str | None = None
    proof_metadata: dict | None = None


# ── Core endpoints ────────────────────────────────────────────────────────────

@app.post("/start-signal", response_model=dict, dependencies=[Depends(verify_api_key)])
def start_signal(body: StartSignalRequest, db: Session = Depends(get_db)):
    """Enqueue a new inference job and return its job_id."""
    params = body.model_dump(exclude_none=True)

    job = Job(status="pending", params=params)
    db.add(job)
    db.commit()
    db.refresh(job)

    # Enqueue RQ task; the worker will call agent_runner.run_signal_job(job.id)
    signal_queue.enqueue(
        "agent_runner.run_signal_job",
        job.id,
        job_timeout=120,
    )
    logger.info("Enqueued job %s  params=%s", job.id, params)
    return {"job_id": job.id, "status": "pending"}


@app.get("/signal-status/{job_id}", response_model=JobStatusResponse)
def signal_status(job_id: str, db: Session = Depends(get_db)):
    """Return current job status; includes signal data when status='done'."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    signal_data = None
    if job.status == "done" and job.signal:
        s = job.signal
        signal_data = {
            "signal": s.signal,
            "confidence": s.confidence,
            "score": s.score,
            "reasoning": s.reasoning,
            "indicators": s.indicators,
        }

    return JobStatusResponse(
        job_id=job_id,
        status=job.status,
        signal=signal_data,
        error=job.error,
    )


@app.get("/fetch-proof/{job_id}", response_model=ProofResponse)
def fetch_proof(job_id: str, db: Session = Depends(get_db)):
    """Return proof metadata and storage URL for a completed job."""
    proof = db.query(Proof).filter(Proof.job_id == job_id).first()
    if not proof:
        raise HTTPException(status_code=404, detail="Proof not found (job may still be running)")

    return ProofResponse(
        job_id=job_id,
        proof_hash=proof.proof_hash,
        storage_url=proof.storage_url,
        proof_metadata=proof.proof_metadata,
    )


@app.get("/proofs/{filename}")
def serve_proof_file(filename: str):
    """Serve a locally stored proof JSON file."""
    path = PROOFS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Proof file not found")
    return FileResponse(path, media_type="application/json")


# ── Claude plugin mirror endpoints ────────────────────────────────────────────

@app.post("/api/plugin/start-signal", response_model=dict, dependencies=[Depends(verify_api_key)])
def plugin_start_signal(body: StartSignalRequest, db: Session = Depends(get_db)):
    return start_signal(body, db)


@app.get("/api/plugin/status/{job_id}", response_model=JobStatusResponse)
def plugin_status(job_id: str, db: Session = Depends(get_db)):
    return signal_status(job_id, db)


@app.get("/api/plugin/fetch-proof/{job_id}", response_model=ProofResponse)
def plugin_fetch_proof(job_id: str, db: Session = Depends(get_db)):
    return fetch_proof(job_id, db)


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}
