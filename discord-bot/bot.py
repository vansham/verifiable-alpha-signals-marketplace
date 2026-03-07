"""
discord-bot/bot.py – Discord bot for the Verifiable Alpha Signals Marketplace.

Commands:
  /request-signal  ticker timeframe  – start a new signal job
  /signal-status   job_id            – poll job status
  /publish         job_id            – post the completed signal + proof link to the channel

Environment variables required:
  DISCORD_TOKEN       – your Discord bot token
  BACKEND_URL         – base URL of the VASM backend (default: http://localhost:8000)
  BACKEND_API_KEY     – API key for the backend (Bearer token)

Install:
  pip install discord.py httpx python-dotenv

Run:
  cd discord-bot
  python bot.py
"""
import logging
import os

import discord
import httpx
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

DISCORD_TOKEN: str = os.environ["DISCORD_TOKEN"]
BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_API_KEY: str = os.getenv("BACKEND_API_KEY", "change-me-backend-api-key")

HEADERS = {"Authorization": f"Bearer {BACKEND_API_KEY}", "Content-Type": "application/json"}
HTTP_TIMEOUT = 20

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _post(path: str, payload: dict) -> dict:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(f"{BACKEND_URL}{path}", json=payload, headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


async def _get(path: str) -> dict:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.get(f"{BACKEND_URL}{path}", headers=HEADERS)
        resp.raise_for_status()
        return resp.json()


# ── Slash commands ────────────────────────────────────────────────────────────

@tree.command(name="request-signal", description="Request a new verifiable trading signal")
@app_commands.describe(ticker="Asset ticker (e.g. BTC)", timeframe="Candle timeframe (e.g. 1h)")
async def request_signal(interaction: discord.Interaction, ticker: str = "BTC", timeframe: str = "1h"):
    await interaction.response.defer(thinking=True)
    try:
        data = await _post("/start-signal", {"ticker": ticker, "timeframe": timeframe})
        job_id = data.get("job_id", "unknown")
        await interaction.followup.send(
            f"✅ Signal job started!\n"
            f"**Job ID:** `{job_id}`\n"
            f"**Ticker:** {ticker}  **Timeframe:** {timeframe}\n"
            f"Use `/signal-status {job_id}` to check progress."
        )
    except Exception as exc:
        logger.exception("request-signal failed")
        await interaction.followup.send(f"❌ Failed to start signal job: {exc}")


@tree.command(name="signal-status", description="Check the status of a signal job")
@app_commands.describe(job_id="The job ID returned by /request-signal")
async def signal_status(interaction: discord.Interaction, job_id: str):
    await interaction.response.defer(thinking=True)
    try:
        data = await _get(f"/signal-status/{job_id}")
        status = data.get("status", "unknown")

        if status == "done" and data.get("signal"):
            s = data["signal"]
            msg = (
                f"📊 **Signal ready!**\n"
                f"**Job:** `{job_id}`\n"
                f"**Signal:** {s.get('signal')}  "
                f"**Confidence:** {s.get('confidence')}  "
                f"**Score:** {s.get('score')}\n"
                f"**Reasoning:** {s.get('reasoning', '')[:200]}\n"
                f"Use `/publish {job_id}` to post it to the channel."
            )
        elif status == "failed":
            msg = f"❌ Job `{job_id}` failed: {data.get('error', 'unknown error')}"
        else:
            msg = f"⏳ Job `{job_id}` is **{status}**. Check back shortly."

        await interaction.followup.send(msg)
    except Exception as exc:
        logger.exception("signal-status failed")
        await interaction.followup.send(f"❌ Could not fetch status: {exc}")


@tree.command(name="publish", description="Publish a completed signal + proof link to the channel")
@app_commands.describe(job_id="The completed job ID")
async def publish(interaction: discord.Interaction, job_id: str):
    await interaction.response.defer(thinking=True)
    try:
        status_data = await _get(f"/signal-status/{job_id}")
        proof_data = await _get(f"/fetch-proof/{job_id}")

        if status_data.get("status") != "done":
            await interaction.followup.send(f"⚠️ Job `{job_id}` is not done yet (status: {status_data.get('status')}).")
            return

        s = status_data.get("signal", {})
        embed = discord.Embed(
            title=f"🔔 Alpha Signal: {s.get('signal', 'N/A')}",
            color=discord.Color.green() if s.get("signal") == "BUY"
                  else (discord.Color.red() if s.get("signal") == "SELL" else discord.Color.gold()),
        )
        embed.add_field(name="Confidence", value=s.get("confidence", "—"), inline=True)
        embed.add_field(name="Score", value=s.get("score", "—"), inline=True)
        embed.add_field(name="Reasoning", value=(s.get("reasoning") or "")[:500], inline=False)
        embed.add_field(name="Proof Hash", value=f"`{proof_data.get('proof_hash', 'N/A')}`", inline=False)
        embed.add_field(name="Proof URL", value=proof_data.get("storage_url", "N/A"), inline=False)
        embed.set_footer(text=f"Job ID: {job_id}")

        await interaction.followup.send(embed=embed)
    except Exception as exc:
        logger.exception("publish failed")
        await interaction.followup.send(f"❌ Could not publish signal: {exc}")


# ── Bot lifecycle ─────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    await tree.sync()
    logger.info("Logged in as %s (ID: %s) — slash commands synced", bot.user, bot.user.id)


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
