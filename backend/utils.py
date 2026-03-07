"""
utils.py – Helpers for proof storage (local or S3) and hashing.
"""
import hashlib
import json
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

USE_S3: bool = os.getenv("USE_S3", "false").lower() in ("true", "1", "yes")
AWS_ACCESS_KEY_ID: str = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY: str = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET: str = os.getenv("S3_BUCKET", "vasm-proofs")
BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")

# Local proofs directory (resolved relative to this file's location)
LOCAL_PROOFS_DIR = Path(__file__).parent / "proofs"
LOCAL_PROOFS_DIR.mkdir(parents=True, exist_ok=True)


def compute_proof_hash(proof_data: dict) -> str:
    """Return the sha256 hex digest of the canonical JSON representation."""
    canonical = json.dumps(proof_data, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save_proof(job_id: str, proof_data: dict) -> str:
    """
    Persist proof JSON and return a URL/path string for storage in DB.

    - USE_S3=true  → upload to S3 and return the s3:// URI
    - USE_S3=false → write to ./proofs/<job_id>.json and return a local URL
    """
    filename = f"{job_id}.json"
    content = json.dumps(proof_data, indent=2, sort_keys=True).encode("utf-8")

    if USE_S3:
        return _save_to_s3(filename, content)
    return _save_locally(filename, content)


# ── Private helpers ───────────────────────────────────────────────────────────

def _save_locally(filename: str, content: bytes) -> str:
    path = LOCAL_PROOFS_DIR / filename
    path.write_bytes(content)
    logger.info("Proof saved locally: %s", path)
    # Expose via a predictable endpoint on the backend
    return f"{BASE_URL}/proofs/{filename}"


def _save_to_s3(filename: str, content: bytes) -> str:
    import boto3  # lazy import; only needed when USE_S3=true
    from botocore.exceptions import BotoCoreError, ClientError

    s3_key = f"proofs/{filename}"
    try:
        s3 = boto3.client(
            "s3",
            region_name=AWS_REGION,
            aws_access_key_id=AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
        )
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=content,
            ContentType="application/json",
        )
        url = f"s3://{S3_BUCKET}/{s3_key}"
        logger.info("Proof uploaded to S3: %s", url)
        return url
    except (BotoCoreError, ClientError) as exc:
        logger.error("S3 upload failed: %s", exc)
        raise
