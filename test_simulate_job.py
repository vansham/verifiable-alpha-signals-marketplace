#!/usr/bin/env python3
"""
test_simulate_job.py – End-to-end smoke test for VASM.

Works entirely with MOCK_OG=true (no external API keys needed).
Starts a signal job, polls until done, and asserts proof is available.

Usage:
    # With running docker compose stack:
    BACKEND_URL=http://localhost:8000 BACKEND_API_KEY=change-me-backend-api-key python test_simulate_job.py

    # Or with custom params:
    python test_simulate_job.py --ticker ETH --timeframe 4h
"""
import argparse
import json
import os
import sys
import time

import httpx

BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_API_KEY: str = os.getenv("BACKEND_API_KEY", "change-me-backend-api-key")
HEADERS = {"Authorization": f"Bearer {BACKEND_API_KEY}", "Content-Type": "application/json"}

POLL_INTERVAL = 2   # seconds between status checks
MAX_POLLS = 30      # give up after 60 seconds


def _print(msg: str):
    print(msg, flush=True)


def start_job(ticker: str, timeframe: str) -> str:
    _print(f"\n[1/4] Starting signal job  ticker={ticker}  timeframe={timeframe}")
    resp = httpx.post(
        f"{BACKEND_URL}/start-signal",
        json={"ticker": ticker, "timeframe": timeframe},
        headers=HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    job_id = data["job_id"]
    _print(f"      → job_id: {job_id}  status: {data.get('status')}")
    return job_id


def poll_status(job_id: str) -> dict:
    _print(f"\n[2/4] Polling status for job {job_id} ...")
    for attempt in range(1, MAX_POLLS + 1):
        resp = httpx.get(f"{BACKEND_URL}/signal-status/{job_id}", headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status", "unknown")
        _print(f"      attempt {attempt:02d}/{MAX_POLLS}  status={status}")

        if status == "done":
            _print("      → Job done!")
            return data
        if status == "failed":
            _print(f"      → Job FAILED: {data.get('error')}")
            sys.exit(1)

        time.sleep(POLL_INTERVAL)

    _print("      → Timed out waiting for job to complete.")
    sys.exit(1)


def fetch_proof(job_id: str) -> dict:
    _print(f"\n[3/4] Fetching proof for job {job_id} ...")
    resp = httpx.get(f"{BACKEND_URL}/fetch-proof/{job_id}", headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    _print(f"      → proof_hash: {data.get('proof_hash')}")
    _print(f"      → storage_url: {data.get('storage_url')}")
    return data


def assert_results(status_data: dict, proof_data: dict):
    _print("\n[4/4] Assertions ...")

    # Signal assertions
    signal = status_data.get("signal") or {}
    assert status_data["status"] == "done", f"Expected status=done, got {status_data['status']}"
    assert signal.get("signal") in ("BUY", "SELL", "HOLD", "NEUTRAL"), f"Unexpected signal: {signal.get('signal')}"
    assert signal.get("confidence") in ("HIGH", "MEDIUM", "LOW"), f"Unexpected confidence: {signal.get('confidence')}"
    assert signal.get("score"), "Missing score"
    assert signal.get("reasoning"), "Missing reasoning"
    # indicators optional in live LLM response
    # assert signal.get("indicators"), "Missing indicators"

    # Proof assertions
    assert proof_data.get("proof_hash"), "Missing proof_hash"
    assert len(proof_data["proof_hash"]) == 64, "proof_hash should be 64-char sha256 hex"
    assert proof_data.get("storage_url"), "Missing storage_url"

    _print("      ✅ All assertions passed!")


def print_summary(status_data: dict, proof_data: dict):
    _print("\n" + "=" * 60)
    _print("VASM SMOKE TEST – RESULT SUMMARY")
    _print("=" * 60)
    s = status_data.get("signal", {})
    _print(f"  Signal:     {s.get('signal')}")
    _print(f"  Confidence: {s.get('confidence')}")
    _print(f"  Score:      {s.get('score')}")
    _print(f"  Reasoning:  {(s.get('reasoning') or '')[:100]}...")
    _print(f"  Proof hash: {proof_data.get('proof_hash')}")
    _print(f"  Stored at:  {proof_data.get('storage_url')}")
    _print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="VASM end-to-end smoke test")
    parser.add_argument("--ticker", default="BTC", help="Asset ticker")
    parser.add_argument("--timeframe", default="1h", help="Candle timeframe")
    args = parser.parse_args()

    _print(f"Backend: {BACKEND_URL}")

    job_id = start_job(args.ticker, args.timeframe)
    status_data = poll_status(job_id)
    proof_data = fetch_proof(job_id)
    assert_results(status_data, proof_data)
    print_summary(status_data, proof_data)


if __name__ == "__main__":
    main()
