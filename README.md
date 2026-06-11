# CodeReview Agent 🤖

[![CI/CD](https://github.com/ompathakbaap/codereview-agent/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/ompathakbaap/codereview-agent/actions)

AI-powered real-time collaborative code review with **Fix-It Mode**. Paste code or a GitHub PR URL → a **LangGraph agent** reviews it for bugs, security, style, and performance — streaming tokens live via SSE. When the review is done, hit **Fix-It** and Groq generates a fully corrected version of your code with a live diff and per-issue explanations.

**100% free to run. No Docker. No AWS. No Kafka.**

---

## Features

- 🤖 **LangGraph agent** — 4 parallel review nodes (bugs, security, style, performance)
- ⚡ **Live SSE streaming** — see each analysis node stream tokens in real time
- 🔁 **Fix-It Mode** — AI generates corrected code + streams an explanation per issue with a live diff view
- 🔗 **GitHub PR diff review** — paste a PR URL and the agent fetches + reviews the diff
- 📊 **Analytics dashboard** — issue trends by category, severity, and language
- 👥 **Real-time collaboration** — multiple users in the same review room via WebSocket + Redis Pub/Sub
- 🛡️ **Rate limiting** — slowapi protects the AI endpoint from quota abuse
- 🔐 **JWT auth** — register/login, all endpoints protected

---

## Stack

| Layer | Tech | Cost |
|---|---|---|
| Frontend | Next.js 15 | Vercel free tier |
| Backend | FastAPI + WebSockets | Railway free tier |
| AI Agent | LangGraph + Groq (llama-3.3-70b) | Groq free tier |
| Realtime | Redis Pub/Sub | Upstash free tier |
| Streaming | Server-Sent Events (SSE) | — |
| Database | PostgreSQL | Neon.tech free tier |
| CI/CD | GitHub Actions | Free |

---

## Free Services You Need

1. **[neon.tech](https://neon.tech)** → New Project → copy connection string → `DATABASE_URL`
2. **[upstash.com](https://upstash.com)** → Create Redis → copy Redis URL → `REDIS_URL`
3. **[console.groq.com/keys](https://console.groq.com/keys)** → New API Key → `GROQ_API_KEY`

---

## LangGraph Agent Architecture

```
START
  └─► analyze_structure
        ├─► bug_check        ──┐
        ├─► security_check   ──┤  (parallel + SSE-streamed)
        ├─► style_check      ──┤
        └─► performance_check──┘
              └─► aggregate
                    └─► END

Fix-It Mode (separate flow, triggered manually):
  START → plan_fixes → generate_fixed_code (streamed) → explain_changes (per-issue, streamed) → END
```

---

## Local Development

### 1. Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Fill in DATABASE_URL, REDIS_URL, GROQ_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
echo "NEXT_PUBLIC_WS_URL=ws://localhost:8000" >> .env.local
npm run dev
```

Open http://localhost:3000

---

## Deployment (Free)

### Backend → Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub → select `backend/`
2. Add env vars (see `.env.example`)
3. Get your URL: `https://codereview-xxx.up.railway.app`

### Frontend → Vercel

```bash
cd frontend
npx vercel
# Set env vars:
# NEXT_PUBLIC_API_URL=https://your-backend.up.railway.app
# NEXT_PUBLIC_WS_URL=wss://your-backend.up.railway.app
```

### CI/CD — GitHub Actions

Add to `Settings → Secrets`:

| Secret | Source |
|--------|--------|
| `RAILWAY_TOKEN` | Railway → Account Settings → Tokens |
| `VERCEL_TOKEN` | Vercel → Account Settings → Tokens |
| `VERCEL_ORG_ID` | `vercel link` → `.vercel/project.json` |
| `VERCEL_PROJECT_ID` | same file |

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/auth/register` | Register |
| POST | `/api/auth/login` | Login → JWT |
| POST | `/api/reviews` | Create review (code paste) |
| POST | `/api/reviews/from-pr` | Create review from GitHub PR URL |
| GET | `/api/reviews` | List your reviews |
| GET | `/api/reviews/stats` | Trend metrics |
| GET | `/api/reviews/{id}` | Get review + issues |
| GET | `/api/reviews/{id}/stream` | **SSE** — stream live agent tokens |
| POST | `/api/reviews/{id}/comments` | Add comment |
| WS | `/ws/review/{id}?token=JWT` | Join real-time room |
| GET | `/api/fix/{id}` | Get review info for Fix-It |
| GET | `/api/fix/{id}/stream` | **SSE** — stream Fix-It progress |

---

## Environment Variables

See `backend/.env.example`. Required:

```bash
DATABASE_URL=postgresql+asyncpg://...neon.tech/...
REDIS_URL=rediss://...upstash.io:6379
GROQ_API_KEY=gsk_...
SECRET_KEY=<random 32-char string>
FRONTEND_URL=https://your-app.vercel.app
```

Optional:
```bash
GITHUB_TOKEN=ghp_...   # avoids GitHub rate limits; needed for private repos
```
