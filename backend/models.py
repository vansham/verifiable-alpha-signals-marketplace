"""
models.py – ORM models: User, Job, Signal, Proof.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, DateTime, ForeignKey, JSON, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from db import Base


def _now():
    return datetime.now(timezone.utc)


def _uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    username = Column(String(128), unique=True, nullable=False)
    email = Column(String(256), unique=True, nullable=True)
    api_key = Column(String(64), unique=True, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    jobs = relationship("Job", back_populates="user")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    status = Column(
        SAEnum("pending", "running", "done", "failed", name="job_status"),
        default="pending",
        nullable=False,
    )
    # Input parameters passed to the inference call
    params = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now)

    user = relationship("User", back_populates="jobs")
    signal = relationship("Signal", back_populates="job", uselist=False)
    proof = relationship("Proof", back_populates="job", uselist=False)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_id = Column(String(36), ForeignKey("jobs.id"), unique=True, nullable=False)
    # Structured signal payload returned by the model
    signal = Column(String(16), nullable=True)       # e.g. "BUY" / "SELL" / "HOLD"
    confidence = Column(String(16), nullable=True)   # e.g. "HIGH"
    score = Column(String(16), nullable=True)        # e.g. "0.87"
    reasoning = Column(Text, nullable=True)
    indicators = Column(JSON, nullable=True)
    raw_output = Column(JSON, nullable=True)         # full model response
    created_at = Column(DateTime(timezone=True), default=_now)

    job = relationship("Job", back_populates="signal")


class Proof(Base):
    __tablename__ = "proofs"

    id = Column(String(36), primary_key=True, default=_uuid)
    job_id = Column(String(36), ForeignKey("jobs.id"), unique=True, nullable=False)
    proof_hash = Column(String(64), nullable=True)   # sha256 hex of proof JSON
    storage_url = Column(Text, nullable=True)        # S3 URL or local path
    proof_metadata = Column(JSON, nullable=True)     # raw proof object from OG
    created_at = Column(DateTime(timezone=True), default=_now)

    job = relationship("Job", back_populates="proof")
