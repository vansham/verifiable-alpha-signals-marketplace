# Verifiable Alpha Signals Marketplace (VASM)

A marketplace for paid, verifiable trading signals.
**OpenGradient** provides cryptographic model-inference attestations (x402 / SDK).
**FastAPI** serves the API. **RQ + Redis** handles async job processing.
**Postgres** stores all state. A **Discord bot** lets communities trigger signals.
A **Claude plugin** exposes the API to LLM-powered assistants.

---

## Architecture

```
Discord / Claude Plugin / Direct API
         │
         ▼
  ┌──────────────┐   enqueue    ┌───────────┐
  │  FastAPI      │ ──────────► │   Redis   │
  │  (backend)    │             │   Queue   │
  └──────────────┘             └─────┬─────┘
         │                           │ dequeue
         │                     ┌─────▼──────────┐
         │                     │  RQ Worker     │
         │                     │  agent_runner  │
         │                     │  ↓ og_client   │
         │                     │  ↓ mock / SDK  │
         │                     │    / HTTP x402 │
         │                     └─────┬──────────┘
         │                           │
         │  read results       ┌─────▼──────────┐
         └────────────────────►│   Postgres     │
                               │   + proofs/    │
                               └────────────────┘
```

---

## Quick Start (Docker Compose)

### 1. Clone and configure

```bash
git clone https://github.com/you/verifiable-alpha-signals-marketplace
cd verifiable-alpha-signals-marketplace

# Copy and edit environment file (MOCK_OG=true works without any API keys)
cp backend/.env.example backend/.env
```

Key variables in `backend/.env`:

| Variable | Description | Default |
|---|---|---|
| `MOCK_OG` | Use deterministic mock OG responses | `true` |
| `OPENGRADIENT_API_KEY` | Real OG API key (leave blank to stay in mock mode) | _(empty)_ |
| `BACKEND_API_KEY` | Auth key for the backend API | `change-me-backend-api-key` |
| `USE_S3` | Upload proofs to S3 instead of local disk | `false` |
| `SECRET_KEY` | App secret (rotate in production) | `change-me` |

### 2. Build and start

```bash
docker compose up --build
```

Services start in order: `db` → `redis` → `backend` → `worker`.
Backend is available at **http://localhost:8000**.
Interactive API docs: **http://localhost:8000/docs**

### 3. Run the smoke test

```bash
# In another terminal (stack must be running)
pip install httpx
python test_simulate_job.py
```

Expected output:
```
[1/4] Starting signal job  ticker=BTC  timeframe=1h
      → job_id: <uuid>  status: pending
[2/4] Polling status for job <uuid> ...
      attempt 01/30  status=pending
      attempt 02/30  status=done
      → Job done!
[3/4] Fetching proof for job <uuid> ...
      → proof_hash: <64-char sha256>
      → storage_url: http://localhost:8000/proofs/<uuid>.json
[4/4] Assertions ...
      ✅ All assertions passed!
```

---

## Running the Worker Standalone

If you want to run the worker outside Docker:

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # edit DATABASE_URL and REDIS_URL to point to local services
rq worker signals --url redis://localhost:6379/0
```

---

## API Reference

All endpoints requiring auth accept:
- `Authorization: Bearer <BACKEND_API_KEY>` header, or
- `X-API-Key: <BACKEND_API_KEY>` header

### `POST /start-signal`
Start a new inference job.

```bash
curl -X POST http://localhost:8000/start-signal \
  -H "Authorization: Bearer change-me-backend-api-key" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "BTC", "timeframe": "1h"}'
```

### `GET /signal-status/{job_id}`
Poll job status. Returns signal when `status=done`.

```bash
curl http://localhost:8000/signal-status/<job_id>
```

### `GET /fetch-proof/{job_id}`
Get proof hash, storage URL, and full proof metadata.

```bash
curl http://localhost:8000/fetch-proof/<job_id>
```

---

## OpenGradient Integration

### Mock mode (no key required)
Set `MOCK_OG=true` in `.env`. The worker returns deterministic fake responses.

### HTTP x402 (copy/paste curl example)
```bash
curl -X POST "https://api.opengradient.ai/v1/infer" \
  -H "Authorization: Bearer $OPENGRADIENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "og/alpha-signal-v1",
    "inputs": {
      "ticker": "BTC",
      "timeframe": "1h",
      "response_format": "json_only",
      "fields": ["signal","confidence","score","reasoning","indicators"]
    },
    "options": {
      "verify": true,
      "attest": true
    }
  }'
```

### SDK (when `opengradient` Python package is available)
Install: `pip install opengradient`  
Set `OPENGRADIENT_API_KEY` in `.env`. The worker auto-detects and uses the SDK.

---

## Discord Bot Setup

1. Create a Discord application at https://discord.com/developers/applications
2. Add a bot, copy the token
3. Set in `backend/.env`:
   ```
   DISCORD_TOKEN=your-bot-token
   BACKEND_URL=http://localhost:8000
   BACKEND_API_KEY=change-me-backend-api-key
   ```
4. Run the bot:
   ```bash
   cd discord-bot
   pip install discord.py httpx python-dotenv
   python bot.py
   ```

Commands:
- `/request-signal BTC 1h` – start a signal job
- `/signal-status <job_id>` – check status
- `/publish <job_id>` – post signal embed with proof to channel

---

## Claude Plugin Setup

1. Deploy the backend to a public URL
2. Edit `claude-plugin/plugin.json` – replace `http://localhost:8000` with your URL
3. Edit `claude-plugin/manifest.yaml` – update `base_url`
4. Register the plugin in Claude's developer console, providing your API key

---

## LangChain Agent

```bash
cd agent
pip install langchain langchain-openai python-dotenv
OPENAI_API_KEY=sk-... MOCK_OG=true python run_agent.py --asset ETH --timeframe 4h
```

---

## S3 Proof Storage

Set in `.env`:
```
USE_S3=true
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
S3_BUCKET=vasm-proofs
```

Proofs are uploaded to `s3://vasm-proofs/proofs/<job_id>.json`. The `storage_url` field in the proof DB row will contain the S3 URI.

---

## Production Notes

**Security & Keys**
Keep `SECRET_KEY`, `BACKEND_API_KEY`, and `OPENGRADIENT_API_KEY` out of version control.
Use a secrets manager (AWS Secrets Manager, HashiCorp Vault, or Docker Secrets) in production.
Rotate keys regularly. Restrict CORS to your frontend domain.

**Cost Management**
OpenGradient inference calls may incur per-call costs. Cache identical (ticker, timeframe, model) requests for a short TTL using Redis. Throttle free-tier users with a rate limiter (e.g. `slowapi`) on the `/start-signal` endpoint. Monitor queue depth and set job time limits.

**On-chain Proof Anchoring (optional)**
To make proofs tamper-evident on-chain, compute `proof_hash` (sha256 of the proof JSON — already in the DB) and submit it as calldata in a minimal Ethereum transaction:

```bash
# Example using cast (Foundry)
cast send \
  --rpc-url $RPC_URL \
  --private-key $PRIVATE_KEY \
  0x000000000000000000000000000000000000dEaD \
  "0x$(echo -n $PROOF_HASH | xxd -p)"
```

Store the resulting `tx_hash` in the `Proof.proof_metadata` JSON column for buyers to audit independently. This costs ~21 000 gas (~$0.02 on L2s such as Base or Arbitrum).

**Scaling**
- Add more RQ workers: `docker compose scale worker=4`
- Add Postgres read replicas for high read volume
- Use CloudFront or a CDN in front of S3 proof files

---

## Folder Structure

```
verifiable-alpha-signals-marketplace/
├── backend/
│   ├── app.py            # FastAPI app + endpoints
│   ├── db.py             # SQLAlchemy engine + session
│   ├── models.py         # ORM: User, Job, Signal, Proof
│   ├── og_client.py      # OG inference: mock / SDK / HTTP x402
│   ├── mock_og.py        # Deterministic offline mock
│   ├── agent_runner.py   # RQ worker task
│   ├── utils.py          # Proof storage + hashing
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .env.example
├── agent/
│   ├── og_tool.py        # LangChain Tool wrapping og_client
│   └── run_agent.py      # Example agent script
├── claude-plugin/
│   ├── plugin.json       # OpenAI-style plugin manifest
│   └── manifest.yaml     # Claude plugin manifest
├── discord-bot/
│   └── bot.py
├── docker-compose.yml
├── test_simulate_job.py
└── README.md
```
