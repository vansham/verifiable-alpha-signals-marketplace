"""
agent/og_tool.py – LangChain Tool that wraps the OpenGradient inference client.

Usage in a LangChain agent:
    from og_tool import og_infer_tool
    tools = [og_infer_tool]
"""
import json
import sys
import os

# Allow importing backend modules when running from the agent/ directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from langchain.tools import Tool  # type: ignore
import og_client  # type: ignore


def _run_og_infer(input_str: str) -> str:
    """
    Execute OpenGradient inference.

    Accepts a JSON string with keys:
      ticker    (str)   – e.g. "BTC"
      timeframe (str)   – e.g. "1h"
      model_id  (str)   – optional; defaults to env OPENGRADIENT_MODEL_ID

    Returns a JSON string with the full inference result (output + proof).
    """
    try:
        params = json.loads(input_str)
    except json.JSONDecodeError as exc:
        return json.dumps({"error": f"Invalid JSON input: {exc}"})

    try:
        result = og_client.infer(params)
        return json.dumps(result, indent=2)
    except Exception as exc:
        return json.dumps({"error": str(exc)})


og_infer_tool = Tool(
    name="og_infer",
    func=_run_og_infer,
    description=(
        "Call OpenGradient to run verifiable model inference and return a trading signal. "
        "Input must be a JSON string with keys: ticker (str), timeframe (str), "
        "and optionally model_id (str). "
        "Returns JSON with 'output' (signal, confidence, score, reasoning, indicators) "
        "and 'proof' (attestation metadata)."
    ),
)
