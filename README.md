# POC Chat Routing

FastAPI + React POC for thesis chat routing with SVM intent classification.

On first user message, the backend classifies intent (TF-IDF + LinearSVC), assigns an online agent that handles that intent (lowest load), and streams updates over WebSocket.

## Prerequisites

- Python **3.13+** and [uv](https://docs.astral.sh/uv/)
- Node.js **20+** and npm
- Trained model at `training/model/svm_intent_pipeline.joblib` (already included, or retrain via `training/`)

## Project Structure

```text
poc-chat-routing/
├── app/
│   ├── main.py             # API, WebSocket; serves SPA in production
│   ├── static/             # Frontend production build target
│   ├── router/
│   ├── services/
│   └── ws/
├── frontend/               # React + Vite (builds into app/static)
├── training/
├── seed.py
├── .env.example
└── requirements.txt
```

## Setup

Commands below use `uv run` so you do **not** need `source .venv/bin/activate`.

```bash
# Backend
uv venv --python 3.13
uv pip install -r requirements.txt
cp .env.example .env

# Seed intents + agents (once)
uv run python seed.py

# Frontend deps
cd frontend && npm install && cd ..
```

## Development

`APP_ENV=development` (default): backend is API/WebSocket only. Use Vite for the UI.

```bash
# Terminal 1 — API + WebSocket
uv run uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend HMR (proxies /api and /ws → :8000)
cd frontend && npm run dev
```

- Chat: http://localhost:5173/chat
- Admin: http://localhost:5173/admin
- Docs: http://localhost:8000/docs

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

## How routing works

1. `POST /api/chat/start` — create user + waiting session
2. `POST /api/chat/send` — classify message intent → assign matching online agent
3. WebSocket `/ws/client/{session_id}` and `/ws/admin` — live updates

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
| `POST` | `/api/chat/start` | Start chat session |
| `POST` | `/api/chat/send` | Send message + classify/route |
| `GET` | `/api/admin/sessions` | List live sessions (excludes archived) |
| `GET` | `/api/admin/sessions/grouped` | Live sessions grouped by agent role |
| `GET` | `/api/admin/sessions/archived` | List archived sessions |
| `GET` | `/api/admin/sessions/{id}/messages` | Session messages |
| `POST` | `/api/admin/sessions/{id}/archive` | Archive session (soft) |
| `POST` | `/api/admin/sessions/{id}/restore` | Restore archived session to live board |
| `DELETE` | `/api/admin/sessions/{id}` | Permanently delete session + messages |
| `POST` | `/api/admin/reply` | Agent reply |
| `GET` | `/api/admin/agents` | List agents |
| `GET` | `/api/admin/intents` | List intents |
| `WS` | `/ws/admin` | Admin live feed |
| `WS` | `/ws/client/{session_id}` | Client live feed |

UI: Admin board at `/admin`; archived sessions at `/admin/archive` (restore or hard-delete).

## Notes

- Prefer `uv run …` over activating the venv; it always uses the project `.venv`.
- Use `uvicorn[standard]` (in `requirements.txt`) so WebSockets work.
- Keep `scikit-learn==1.6.1` in sync with the pickled model, or retrain with your installed version.
- Optional: retrain model from `training/` — see `training/README.md`.
