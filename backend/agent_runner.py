"""
agent_runner.py – RQ worker task that processes a single inference job.

Called by `rq worker` when a job is dequeued from the "signals" queue.
Flow:
  1. Mark job as "running"
  2. Call og_client.infer(params)
  3. Parse structured signal from output
  4. Compute proof hash, save proof artifact
  5. Write Signal and Proof rows to DB
  6. Mark job as "done" (or "failed" on exception)
"""
import logging
import os
import sys

# Ensure the backend package is importable when run by the worker
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()

import og_client
from db import SessionLocal
from models import Job, Signal, Proof
from utils import compute_proof_hash, save_proof

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def run_signal_job(job_id: str) -> dict:
    """
    Entry point called by RQ.

    :param job_id: UUID of the Job row to process.
    :returns: Summary dict (used by RQ for the job result).
    """
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Job {job_id!r} not found in DB")

        # ── Mark running ──────────────────────────────────────────────────────
        job.status = "running"
        db.commit()
        logger.info("Job %s started", job_id)

        params: dict = job.params or {}

        # ── Call OpenGradient (or mock) ───────────────────────────────────────
        result = og_client.infer(params)
        output: dict = result.get("output", {})
        proof_data: dict = result.get("proof", {})

        # ── Compute proof hash ────────────────────────────────────────────────
        proof_hash = compute_proof_hash(proof_data)

        # ── Persist proof artifact ────────────────────────────────────────────
        storage_url = save_proof(job_id, proof_data)

        # ── Write Signal row ──────────────────────────────────────────────────
        signal_row = Signal(
            job_id=job_id,
            signal=str(output.get("signal", "")),
            confidence=str(output.get("confidence", "")),
            score=str(output.get("score", "")),
            reasoning=output.get("reasoning"),
            indicators=output.get("indicators"),
            raw_output=output,
        )
        db.add(signal_row)

        # ── Write Proof row ───────────────────────────────────────────────────
        proof_row = Proof(
            job_id=job_id,
            proof_hash=proof_hash,
            storage_url=storage_url,
            proof_metadata=proof_data,
        )
        db.add(proof_row)

        # ── Mark done ─────────────────────────────────────────────────────────
        job.status = "done"
        db.commit()
        logger.info("Job %s completed  signal=%s  proof_hash=%s", job_id, output.get("signal"), proof_hash)

        return {
            "job_id": job_id,
            "signal": output.get("signal"),
            "proof_hash": proof_hash,
            "storage_url": storage_url,
        }

    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = "failed"
                job.error = str(exc)
                db.commit()
        except Exception:
            pass
        raise

    finally:
        db.close()
