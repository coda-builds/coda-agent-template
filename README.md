<div align="center">

# 🤖 Coda Agent Template

**A production-ready, multi-state conversational AI agent scaffold.**  
Built for rapid client delivery on modern infrastructure.

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136-009688.svg)](https://fastapi.tiangolo.com)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-Llama%203.1%2070B-blue.svg)](https://openrouter.ai)

</div>

---

## Overview

Coda Agent Template is an opinionated, production-structured scaffold for building **stateful conversational AI agents** as client deliverables. Fork this repository, configure the state machine in a single YAML file, deploy to Railway in minutes, and hand over a live, production-grade product.

**What ships out of the box:**

- **Multi-state conversation engine** — define any number of states and transitions in `config/agent_config.yaml`; no code changes needed
- **OpenRouter + Llama 3.3 70B** — fast inference via the OpenRouter API using the free-tier model (`meta-llama/llama-3.3-70b:free`). No credits required. Switch to the paid variant by removing `:free` from the model name when you need higher throughput.
- **Automatic state transitions** — a lightweight secondary LLM call classifies each turn and advances the state machine
- **Supabase persistence** — full conversation history stored in Postgres with Row Level Security
- **REST API** — clean, documented endpoints for chat, conversation retrieval, and resets
- **Railway deployment** — deploy from GitHub in minutes with health checks, auto-restart, and environment variable management
- **24 passing tests** — full unit and integration test coverage of the state machine, API layer, and error paths

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          Client (HTTP)                          │
└────────────────────────────┬────────────────────────────────────┘
                             │ POST /api/v1/chat
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI App                              │
│                                                                 │
│  ┌──────────────┐    ┌──────────────────────────────────────┐  │
│  │  /health     │    │          StateMachine                │  │
│  │  (Railway    │    │                                      │  │
│  │  healthcheck)│    │  1. Load conversation from Supabase  │  │
│  └──────────────┘    │  2. Build messages with state prompt │  │
│                      │  3. Call OpenRouter → get reply          │  │
│                      │  4. Call OpenRouter (classifier) → next  │  │
│                      │     state                            │  │
│                      │  5. Persist turn + new state         │  │
│                      │  6. Return ChatResponse              │  │
│                      └──────────────┬───────────────────────┘  │
└─────────────────────────────────────┼───────────────────────────┘
                                      │
               ┌──────────────────────┼──────────────────────┐
               ▼                      ▼                       │
┌──────────────────────┐  ┌─────────────────────────────┐    │
│    OpenRouter API     │  │       Supabase              │    │
│  Llama 3.3 70B       │  │                             │    │
│                      │  │  conversations table        │    │
│  • chat_completion   │  │  messages table             │    │
│  • transition        │  │  (Postgres + RLS)           │    │
│    classifier        │  └─────────────────────────────┘    │
└──────────────────────┘                                      │
                                                              │
                    ┌─────────────────────────────────────────┘
                    │
                    ▼
        config/agent_config.yaml
        (State definitions, system prompts, transitions)
```

### State Machine Flow

Each conversation exists in exactly one state at a time. After every assistant reply, a fast secondary LLM call (temperature=0) classifies the conversation against the current state's transition conditions and advances the state if needed.

```
                              ┌─────────────────────────────────────────┐
                              │  (fallback after max_turns with no match)│
                              ▼                                          │
GREETING ──────────────► INTENT_CLARIFICATION ──► ORDER_INQUIRY ──► CLOSING ──► CLOSED
    │                            │                PRODUCT_SUPPORT ──►   ▲        (terminal)
    │                            └───────────────► RETURNS_REFUNDS ─────┤
    └────────────────────────────────────────────► ESCALATION ──────────┘
```

---

## Quick Start (Local)

### Prerequisites

- Python 3.11 or higher
- An [OpenRouter API key](https://openrouter.ai/keys) (free tier available)
- A [Supabase](https://supabase.com) project (free tier available)

### 1. Clone and set up

```bash
git clone https://github.com/your-username/coda-agent-template.git
cd coda-agent-template

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in:

```dotenv
OPENROUTER_API_KEY=sk-or-your_key_here
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI...
```

### 3. Set up the database

1. Open your Supabase project dashboard
2. Go to **SQL Editor**
3. Paste and run the contents of `scripts/setup_supabase.sql`

This creates the `conversations` and `messages` tables, indexes, and RLS policies.

### 4. Run the server

```bash
uvicorn app.main:app --reload
```

The API is now live at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

### 5. Test it

```bash
# Start a new conversation
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hi, I need help with my order"}'

# Continue the same conversation
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "My order number is #12345 and it has not arrived",
    "conversation_id": "CONVERSATION_ID_FROM_ABOVE"
  }'
```

---

## Deploy to Railway

### Prerequisites

Before deploying, make sure you have:
- Created a [Supabase](https://supabase.com) project and run `scripts/setup_supabase.sql` in the SQL Editor (creates the `conversations` and `messages` tables — the app will crash without them)
- An [OpenRouter API key](https://openrouter.ai/keys)
- This repository pushed to GitHub

### Deployment steps

1. **Create a Railway project** from your GitHub repository at [railway.com](https://railway.com). Railway detects `railway.toml` automatically.

2. **Set environment variables** in the Railway dashboard (Settings → Variables):

   ```bash
   OPENROUTER_API_KEY=sk-or-...
   SUPABASE_URL=https://your-project-id.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=eyJ...
   APP_ENV=production
   LOG_LEVEL=INFO
   ```

   Or via the CLI:
   ```bash
   railway variables set OPENROUTER_API_KEY=sk-or-...
   railway variables set SUPABASE_URL=https://...
   railway variables set SUPABASE_SERVICE_ROLE_KEY=eyJ...
   railway variables set APP_ENV=production
   ```

3. **Deploy**
   ```bash
   railway up
   ```

Railway automatically:
- Runs `pip install -r requirements.txt` via nixpacks
- Injects `$PORT` and starts `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Polls `GET /health` every 30 seconds
- Restarts on failure (up to 3 times)

---

## API Reference

All endpoints accept and return JSON.

### `POST /api/v1/chat`

Send a user message to the agent.

**Request body:**
```json
{
  "message": "I need help with a return",
  "conversation_id": "optional-existing-id",
  "metadata": {
    "user_id": "u_123",
    "locale": "en-GB"
  }
}
```

**Response:**
```json
{
  "conversation_id": "550e8400-e29b-41d4-a716-446655440000",
  "reply": "I'm sorry to hear that. Let me help you with your return. Could you share your order number?",
  "current_state": "RETURNS_REFUNDS",
  "is_terminal": false,
  "turn_count": 2,
  "metadata": { "user_id": "u_123", "locale": "en-GB" }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `conversation_id` | string | UUID for this session. Store and pass back to continue the conversation. |
| `reply` | string | The agent's response text. |
| `current_state` | string | The agent's active state after this turn. |
| `is_terminal` | boolean | When `true`, the conversation is closed. New messages are rejected. |
| `turn_count` | integer | Total turns in this conversation. |

---

### `GET /api/v1/conversations/{conversation_id}`

Retrieve the full conversation history and metadata.

**Response:**
```json
{
  "conversation_id": "550e8400-...",
  "current_state": "ORDER_INQUIRY",
  "turn_count": 4,
  "created_at": "2025-01-15T10:30:00Z",
  "updated_at": "2025-01-15T10:35:00Z",
  "metadata": {},
  "messages": [
    { "role": "user", "content": "Hi", "state": "GREETING", "created_at": "..." },
    { "role": "assistant", "content": "Hello!", "state": "GREETING", "created_at": "..." }
  ]
}
```

---

### `POST /api/v1/conversations/{conversation_id}/reset`

Soft-reset: rewind the state machine to the initial state, preserving message history.

**Request body:**
```json
{ "reason": "User requested fresh start" }
```

---

### `GET /health`

Liveness probe — always returns `200 OK` if the process is running. This is the endpoint Railway polls. It does **not** call OpenRouter or Supabase, so a billing issue or transient API error will never take your deployment offline.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "checks": { "process": "ok" }
}
```

---

### `GET /ready`

Readiness probe — calls OpenRouter and Supabase and returns `200` if both are reachable, `503` if either is down. Use this in your monitoring stack (UptimeRobot, Datadog, etc.) to alert on dependency failures. Do **not** configure Railway to poll this endpoint.

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "checks": {
    "openrouter": "ok",
    "supabase": "ok"
  }
}
```

---

## Customising the State Machine

All agent behaviour is defined in `config/agent_config.yaml`. **You do not need to modify any Python code** to build a completely different agent.

### YAML structure

```yaml
agent_name: "Your Agent Name"
agent_description: "What this agent does."
initial_state: FIRST_STATE   # Must match a state name below

states:
  - name: FIRST_STATE
    description: >
      One sentence describing when/why the agent is in this state.
      The transition classifier reads this.
    system_prompt: |
      You are [agent persona]. Your goal right now is [specific goal].
      
      Guidelines:
      - [rule 1]
      - [rule 2]
      
      Tone: [tone description]
    transitions:
      - condition: >
          Natural language description of when to leave this state.
          The LLM classifier matches the conversation against this.
        next_state: SECOND_STATE
        priority: 1            # Lower = evaluated first
      - condition: "The user is angry or asks for a human."
        next_state: ESCALATION
        priority: 2
    max_turns: 5               # Optional: auto-advance after 5 turns here
    fallback_state: ESCALATION # Optional: state to advance to at max_turns
    is_terminal: false         # Set true for end states

  - name: SECOND_STATE
    # ...

  - name: TERMINAL_STATE
    description: "Conversation is complete."
    system_prompt: "The conversation is over."
    is_terminal: true
    transitions: []
```

### Example: booking agent

Replace the YAML content to transform this into a restaurant booking agent with states like `COLLECT_DATE`, `COLLECT_PARTY_SIZE`, `CONFIRM_BOOKING`, `BOOKING_CONFIRMED` — no Python changes required.

### Example: technical support agent

States: `TRIAGE` → `KNOWN_ISSUE` / `ADVANCED_DEBUGGING` / `ESCALATE_TICKET` → `RESOLVED`.

Each state's `system_prompt` gives the LLM its specific persona, constraints, and instructions for that phase of the conversation.

### Transition classifier tips

- Write transition `condition` fields as plain English — they are read directly by the LLM.
- Be specific: "The user has provided their order number" is better than "The user has answered."
- Use `priority` to create tiebreakers when multiple conditions could match simultaneously.
- Safety-critical exits (anger, escalation requests) should always be **priority 1** so they are evaluated before any other condition. Routine transitions (resolved, thank you) get higher numbers.

---

## Running Tests

```bash
# Run all tests
pytest

# With coverage
pip install pytest-cov
pytest --cov=app --cov-report=term-missing

# Run only unit tests
pytest tests/test_state_machine.py -v

# Run only API tests
pytest tests/test_api.py -v
```

The test suite (24 tests) mocks all external services — no OpenRouter key or Supabase connection needed to run tests.

---

## Project Structure

```
coda-agent-template/
│
├── app/
│   ├── main.py                 # FastAPI app factory + lifespan
│   ├── config.py               # Pydantic Settings (env vars)
│   │
│   ├── agent/
│   │   ├── state_machine.py    # Core orchestration logic
│   │   ├── states.py           # YAML loader + State dataclasses
│   │   └── prompts.py          # Prompt builders
│   │
│   ├── services/
│   │   ├── openrouter_service.py # OpenRouter API wrapper
│   │   └── supabase_service.py # Supabase CRUD
│   │
│   ├── api/routes/
│   │   ├── chat.py             # /chat and /conversations endpoints
│   │   └── health.py           # /health endpoint
│   │
│   └── models/
│       └── schemas.py          # Pydantic request/response models
│
├── config/
│   └── agent_config.yaml       # ← Edit this to build your agent
│
├── scripts/
│   └── setup_supabase.sql      # Run once to create DB schema
│
├── tests/
│   ├── conftest.py             # Shared pytest configuration
│   ├── test_state_machine.py   # Unit tests (state machine, prompts)
│   └── test_api.py             # API integration tests (mocked)
│
├── .env.example                # Copy to .env and fill in secrets
├── railway.toml                # Railway deployment config
├── Procfile                    # Process declaration (mirrors railway.toml start command)
├── requirements.txt
└── pytest.ini
```

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | ✅ | — | Your OpenRouter API key |
| `SUPABASE_URL` | ✅ | — | Your Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | Supabase service-role key (bypasses RLS) |
| `APP_ENV` | | `development` | `development` or `production` |
| `APP_HOST` | | `0.0.0.0` | Host interface to bind (leave as default for Railway) |
| `APP_PORT` | | `8000` | Port to listen on (Railway injects `$PORT`) |
| `LOG_LEVEL` | | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `AGENT_CONFIG_PATH` | | `config/agent_config.yaml` | Path to the agent config YAML |
| `MAX_CONVERSATION_TURNS` | | `50` | Hard limit on turns per session |
| `LLM_MODEL` | | `meta-llama/llama-3.3-70b:free` | OpenRouter model identifier. Free-tier models end in `:free` (20 req/min, 200 req/day). Remove `:free` to use the paid version. |
| `LLM_TEMPERATURE` | | `0.7` | Generation temperature (0–2) |
| `LLM_MAX_TOKENS` | | `1024` | Max tokens per reply |
| `ALLOWED_ORIGINS` | | `*` | Comma-separated CORS origins |

> **Production note:** Set `APP_ENV=production` to disable `/docs` and `/redoc`.

---

## Client Deliverable

This template is designed to be shipped as a **complete, working product** in **4–5 working days**:

| Day | Work |
|-----|------|
| **Day 1** | Fork repository, define states and system prompts in `agent_config.yaml`, set up Supabase schema |
| **Day 2** | Tune prompts against real conversations, adjust transition conditions, configure `metadata` fields for the client's user model |
| **Day 3** | Wire up to the client's front-end or existing platform via the REST API; configure CORS and auth if required |
| **Day 4** | Deploy to Railway, connect the client's domain, configure environment variables, smoke-test all state paths end-to-end |
| **Day 5** | Buffer for iteration, edge-case handling, handover documentation, and client walkthrough |

**What the client receives:**
- A live HTTPS API endpoint on Railway with automatic SSL
- Full conversation persistence in their own Supabase project
- A documented REST API their front-end team can integrate
- The complete source code under their GitHub organisation
- A 1-page internal runbook covering deployment, monitoring, and how to update agent prompts

> The only moving part between client projects is `config/agent_config.yaml`. Python code stays untouched.

---

## Security Notes

- The `SUPABASE_SERVICE_ROLE_KEY` bypasses Row Level Security — keep it server-side only, never expose it in a client application
- Set `ALLOWED_ORIGINS` to your client's specific domain in production; avoid `*`
- In production, `APP_ENV=production` disables the interactive API docs (`/docs`, `/redoc`)
- Rotate the OpenRouter API key immediately if it is ever committed to version control

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-improvement`)
3. Make your changes and ensure all tests pass (`pytest`)
4. Open a pull request

---

## Licence

MIT — use freely in client projects.
