import json
import logging
import os
import re
import time

from dotenv import load_dotenv
from mock_og import mock_infer

load_dotenv()

logger = logging.getLogger(__name__)

MOCK_OG: bool = os.getenv("MOCK_OG", "false").lower() in ("true", "1", "yes")
OPENGRADIENT_API_KEY: str = os.getenv("OPENGRADIENT_API_KEY", "")
MODEL_ID: str = os.getenv("OPENGRADIENT_MODEL_ID", "og/alpha-signal-v1")



def get_market_data(ticker: str) -> dict:
    """Fetch real-time data from CoinGecko"""
    try:
        import requests
        coin_map = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "BNB": "binancecoin", "DOGE": "dogecoin", "ADA": "cardano",
            "XRP": "ripple", "AVAX": "avalanche-2", "MATIC": "matic-network",
        }
        coin_id = coin_map.get(ticker.upper(), ticker.lower())
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd&include_24hr_change=true&include_24hr_vol=true&include_market_cap=true"
        r = requests.get(url, timeout=5)
        data = r.json().get(coin_id, {})
        if data:
            return {
                "price_usd": data.get("usd", "N/A"),
                "change_24h": round(data.get("usd_24h_change", 0), 2),
                "volume_24h": data.get("usd_24h_vol", "N/A"),
                "market_cap": data.get("usd_market_cap", "N/A"),
            }
    except Exception as e:
        logger.warning("CoinGecko failed: %s", e)
    return {}

def infer(params: dict) -> dict:
    if MOCK_OG or not OPENGRADIENT_API_KEY:
        logger.info("OG: MOCK mode")
        return mock_infer(MODEL_ID, params)

    try:
        import opengradient as og
        ticker = params.get("ticker", "BTC")
        timeframe = params.get("timeframe", "1h")

        client = og.Client(private_key=OPENGRADIENT_API_KEY)

        market = get_market_data(ticker)
        market_context = ""
        if market:
            market_context = f"Current {ticker} Price: ${market[\'price_usd\']} | 24h Change: {market[\'change_24h\']}% | Volume: ${market[\'volume_24h\']:,.0f}"
        
        prompt = f"""Analyze {ticker} on {timeframe} timeframe.
{market_context}
Return ONLY this JSON, no other text:
{{
  "signal": "BUY",
  "confidence": "HIGH",
  "score": 0.85,
  "reasoning": "brief reason here",
  "indicators": {{"RSI": 58.2, "MACD": 0.03, "volume_change_pct": 12.4}}
}}
Replace values with your actual analysis. Return ONLY valid JSON."""

        response = client.llm.chat(
            model=og.TEE_LLM.CLAUDE_HAIKU_4_5,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text from TextGenerationOutput
        text = response.chat_output.get("content", "") if isinstance(response.chat_output, dict) else str(response.chat_output)
        logger.info("OG raw text: %s", text[:300])

        # Parse JSON - try multiple strategies
        output = None

        # Strategy 1: ```json blocks
        m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                output = json.loads(m.group(1))
            except Exception:
                pass

        # Strategy 2: raw {} block
        if not output:
            m = re.search(r"(\{.*\})", text, re.DOTALL)
            if m:
                try:
                    output = json.loads(m.group(1))
                except Exception:
                    pass

        # Strategy 3: fallback
        if not output:
            output = {
                "signal": "HOLD",
                "confidence": "LOW",
                "score": 0.5,
                "reasoning": text[:300],
                "indicators": {}
            }

        proof = {
            "attestation_id": getattr(response, "transaction_hash", f"og-live-{int(time.time())}"),
            "model_id": MODEL_ID,
            "timestamp": getattr(response, "tee_timestamp", int(time.time())),
            "tee_signature": getattr(response, "tee_signature", None),
            "payment_hash": getattr(response, "payment_hash", None),
            "mock": False,
        }

        return {"output": output, "proof": proof}

    except Exception as exc:
        logger.exception("OG SDK failed: %s", exc)
        raise
