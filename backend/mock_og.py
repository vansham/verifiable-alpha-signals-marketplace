"""
mock_og.py – Deterministic mock OpenGradient response.

Used when MOCK_OG=true or OPENGRADIENT_API_KEY is absent.
Returns a fixed structure that mimics the real OG inference output so the
entire pipeline can be tested offline.
"""
import hashlib
import json
import time


def mock_infer(model_id: str, payload: dict) -> dict:
    """
    Return a deterministic mock inference result.

    The response shape mirrors what we expect from a real OG call:
      - output: structured signal dict
      - proof: attestation metadata (fake but hash-stable)
    """
    # Build a deterministic seed from the input so the same params always
    # yield the same mock output (useful for regression testing).
    seed_str = json.dumps({"model": model_id, **payload}, sort_keys=True)
    seed_hash = hashlib.sha256(seed_str.encode()).hexdigest()

    # Rotate between BUY/HOLD/SELL based on first nibble of hash
    nibble = int(seed_hash[0], 16)
    signal_map = {
        range(0, 6): "BUY",
        range(6, 11): "HOLD",
        range(11, 16): "SELL",
    }
    signal = next(v for k, v in signal_map.items() if nibble in k)

    output = {
        "signal": signal,
        "confidence": "HIGH" if nibble < 4 else ("MEDIUM" if nibble < 10 else "LOW"),
        "score": round(0.5 + (nibble / 30), 4),
        "reasoning": (
            f"Mock reasoning for model={model_id}. "
            "Trend momentum positive, volume surge detected, RSI 58."
        ),
        "indicators": {
            "RSI": 58.2,
            "MACD": 0.032,
            "BB_upper": 52100,
            "BB_lower": 49800,
            "volume_change_pct": 12.4,
        },
    }

    proof = {
        "model_id": model_id,
        "attestation_id": f"mock-attest-{seed_hash[:16]}",
        "timestamp": int(time.time()),
        "input_hash": seed_hash,
        "output_hash": hashlib.sha256(json.dumps(output, sort_keys=True).encode()).hexdigest(),
        "mock": True,
    }

    return {"output": output, "proof": proof}
