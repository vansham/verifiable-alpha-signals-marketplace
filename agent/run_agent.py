"""
agent/run_agent.py – Example LangChain agent that produces a structured trading signal.

Usage:
    cd agent
    pip install langchain langchain-openai
    OPENAI_API_KEY=sk-... MOCK_OG=true python run_agent.py
"""
import json
import os
import sys

# Load .env from backend if present
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
load_dotenv()  # also check local .env

from langchain.agents import AgentExecutor, create_react_agent
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI  # type: ignore

from og_tool import og_infer_tool

TOOLS = [og_infer_tool]

PROMPT_TEMPLATE = PromptTemplate.from_template(
    """You are a professional algorithmic trading analyst.
Your task is to generate a verifiable alpha signal for the given asset.

Use the `og_infer` tool to call OpenGradient and get a model-backed signal.
Then return a clean JSON object with exactly these keys:
  signal, confidence, score, reasoning, indicators, proof_hash

Asset: {asset}
Timeframe: {timeframe}

{tools}
Tool names: {tool_names}
Scratchpad: {agent_scratchpad}

Return ONLY the final JSON object. Do not add commentary outside the JSON.
"""
)


def run_agent(asset: str = "BTC", timeframe: str = "1h") -> dict:
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
        api_key=os.getenv("OPENAI_API_KEY", ""),
    )

    agent = create_react_agent(llm, TOOLS, PROMPT_TEMPLATE)
    executor = AgentExecutor(agent=agent, tools=TOOLS, verbose=True, max_iterations=3)

    result = executor.invoke({"asset": asset, "timeframe": timeframe})
    output_str: str = result.get("output", "{}")

    # Try to extract JSON from the output
    try:
        # Strip markdown fences if present
        clean = output_str.strip().strip("```json").strip("```").strip()
        signal_json = json.loads(clean)
    except json.JSONDecodeError:
        signal_json = {"raw_output": output_str}

    return signal_json


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run VASM LangChain agent")
    parser.add_argument("--asset", default="BTC")
    parser.add_argument("--timeframe", default="1h")
    args = parser.parse_args()

    result = run_agent(asset=args.asset, timeframe=args.timeframe)
    print(json.dumps(result, indent=2))
