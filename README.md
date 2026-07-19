# POC Chat Routing

FastAPI + React POC for thesis chat routing with SVM intent classification.

On first user message, the backend classifies intent (TF-IDF + LinearSVC), assigns an online agent that handles that intent (lowest load), and streams updates over WebSocket.

Channel: **WhatsApp only** via [WAHA](https://waha.devlike.pro/) (GOWS engine). Pair on `/chat`; agent board on `/admin`.

## Prerequisites

- Python **3.13+** and [uv](https://docs.astral.sh/uv/)
- Node.js **20+** and npm
- Docker (for WAHA WhatsApp)
- Trained model at `training/model/svm_intent_pipeline.joblib` (already included, or retrain via `training/`)

## Project Structure

```text
poc-chat-routing/
├── app/
│   ├── main.py             # API, WebSocket; serves SPA in production
│   ├── router/             # admin, WAHA webhook
│   ├── services/           # classifier, router, waha client, auto-ack
│   ├── static/             # Frontend production build target
│   └── ws/
├── frontend/               # React + Vite (builds into app/static)
├── training/
├── docker-compose.yml      # WAHA GOWS
├── seed.py
├── .env.example
├── pyproject.toml
└── uv.lock
```

## Setup

Commands below use `uv` — no need to activate a venv manually.

```bash
# Backend deps (creates .venv + installs from uv.lock)
uv sync
cp .env.example .env

# Seed intents + agents (once)
uv run python seed.py

# Frontend deps
cd frontend && npm install && cd ..
```

### Schema note (SQLite)

WhatsApp adds `users.phone`, `chat_sessions.channel`, and `messages.external_id`. SQLite `create_all` does not migrate old tables. If you already have a DB from before this feature:

```bash
rm -f chat_routing.db
uv run python seed.py
```

## Development

`APP_ENV=development` (default): backend is API/WebSocket only. Use Vite for the UI.

```bash
# Terminal 1 — API + WebSocket
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend HMR (proxies /api and /ws → :8000)
cd frontend && npm run dev
```

- WhatsApp pairing: http://localhost:5173/chat
- Admin: http://localhost:5173/admin
- Docs: http://localhost:8000/docs

## WhatsApp (WAHA GOWS)

### 1. Start WAHA

```bash
# Uses WAHA_API_KEY from .env (or default in compose)
docker compose up -d
```

If `/api/admin/whatsapp/status` returns **502**, WAHA is unreachable from the host — recreate with the latest compose (`ports: "3000:3000"`, `WHATSAPP_API_HOSTNAME=0.0.0.0`) then:

```bash
docker compose up -d --force-recreate waha
curl -H "X-Api-Key: $WAHA_API_KEY" http://127.0.0.1:3000/ping
```

- WAHA dashboard / Swagger: http://localhost:3000
- Webhook target (from container → host app): `http://host.docker.internal:8000/api/webhooks/waha`

Ensure `.env` has matching keys:

```env
WAHA_BASE_URL=http://localhost:3000
WAHA_API_KEY=waha-secret-change-me
WAHA_SESSION_NAME=default
WAHA_HOOK_HMAC_KEY=waha-hmac-change-me
```

**Apple Silicon vs Intel/AMD:** compose defaults to `devlikeapro/waha:gows-arm`. On amd64 hosts set `WAHA_IMAGE=devlikeapro/waha:gows` in `.env`.

Webhook requests must include a valid `X-Webhook-Hmac` (SHA-512 of the body using `WAHA_HOOK_HMAC_KEY` / `WHATSAPP_HOOK_HMAC_KEY`).

### 2. Pair the business number

1. Open Admin → **WhatsApp** panel
2. Click **Start / reconnect**
3. When status is `SCAN_QR_CODE`, scan the QR with WhatsApp → Linked devices
4. Status becomes `WORKING` when linked

### 3. Routing behavior

| Event | Behavior |
|-------|----------|
| First text (no open session) | Create WhatsApp session → classify → assign agent |
| Further messages while session is open | Sticky: same agent, **no** re-classification |
| Admin **Archive & Close** | Session archived; next message from that chat = new session + classify again |

After each inbound text is accepted, WAHA **read receipt** (`sendSeen`) is sent ~1.5s later.

On the **first** classify/route of a session, the bot sends a one-time auto-ack (stored in the thread):

> Terimakasih sudah menghubungi kami, Pesan anda sudah kami terima dan sudah kami alihkan ke tim {Role}

`{Role}` is the assigned agent role (`Support`, `Tech`, …), defaulting to `Support` if unassigned.

**LID contacts:** WhatsApp/GOWS may identify chats as `…@lid` instead of `…@c.us`. The app stores the original WAHA `chatId` and uses it for replies — do not rebuild LID digits as `@c.us` (that causes `no LID found` errors).

Confirm dialog copy: **Are you sure to archive and close this session?**

POC scope: text messages only (groups / media ignored).

## Production (FE → `app/static`, served by backend)

Vite writes the build straight into `app/static`. With `APP_ENV=production`, FastAPI serves that SPA (`/`, `/chat`, `/admin`, `/assets/...`).

```bash
# 1. Build frontend into app/static
cd frontend
npm install
npm run build
cd ..

# 2. Run backend in production mode
# (or set APP_ENV=production in .env)
APP_ENV=production uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then open:

- http://localhost:8000/chat
- http://localhost:8000/admin
- http://localhost:8000/docs

`GET /api/health` reports `"spa": "true"` when production mode is on and `app/static/index.html` exists.

For production WhatsApp, set `WHATSAPP_HOOK_URL` in compose to a publicly reachable HTTPS URL for `/api/webhooks/waha`.

## How routing works

WhatsApp-only (no web chat widget):

1. Pair the business number on `/chat` (WAHA QR / status)
2. Customer message → `POST /api/webhooks/waha` → classify **once** on first message → assign matching online agent (later messages stay sticky)
3. Auto-ack is sent via WAHA `POST /api/sendText` **before** it appears on the admin board (never dashboard-only)
4. Admin reply → WAHA `sendText` first, then persist; WebSocket `/ws/admin` for live board updates

Intent is always saved on the session. If no online agent matches, the session stays **Unassigned** but still shows the predicted intent.

### Role → intent mapping

| Role | Agent | Intents |
|------|-------|---------|
| `support` | Budi | `complaint`, `cancellation_request`, `refund_request` |
| `tech` | Siti | `technical_support`, `account_data` |
| `marketing` | Rina | `promotions_discounts`, `product_service_info` |
| `finance` | Adi | `payment_inquiry` |
| `logistik` | Dedi | `shipping_information`, `order_status`, `operating_hours_location` |

All 11 dataset intents are covered (one agent per role). Admin board columns: the five roles above + Unassigned.

## Main endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/webhooks/waha` | WAHA inbound webhook |
| `GET` | `/api/admin/sessions` | List live sessions (excludes archived) |
| `GET` | `/api/admin/sessions/grouped` | Live sessions grouped by agent role |
| `GET` | `/api/admin/sessions/archived` | List archived sessions |
| `GET` | `/api/admin/sessions/{id}/messages` | Session messages |
| `POST` | `/api/admin/sessions/{id}/archive` | Archive & close session |
| `POST` | `/api/admin/sessions/{id}/restore` | Restore archived session to live board |
| `DELETE` | `/api/admin/sessions/{id}` | Permanently delete session + messages |
| `POST` | `/api/admin/reply` | Agent reply via WAHA `sendText` (persist only after success) |
| `GET` | `/api/admin/whatsapp/status` | WAHA session status |
| `GET` | `/api/admin/whatsapp/qr` | QR image (base64) when scanning |
| `POST` | `/api/admin/whatsapp/session/start` | Create/start WAHA session |
| `GET` | `/api/admin/agents` | List agents |
| `GET` | `/api/admin/intents` | List intents |
| `WS` | `/ws/admin` | Admin live feed |

UI: WAHA pairing at `/chat`; admin board at `/admin`; archive at `/admin/archive`.

## Notes

- Prefer `uv run …` over activating the venv; it always uses the project `.venv`.
- Use `uvicorn[standard]` (in `pyproject.toml`) so WebSockets work.
- Keep `scikit-learn==1.6.1` in sync with the pickled model, or retrain with your installed version.
- After changing dependencies: `uv add <pkg>` / `uv remove <pkg>`, then commit `uv.lock`.
- Optional: retrain model from `training/` — see `training/README.md`.
- WhatsApp integration uses unofficial WAHA / WhatsApp Web automation; treat as a POC, not production-safe against bans.
