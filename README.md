# LinkMindServices

Backend for LinkMind, a URL shortener that classifies every link with AI and screens it for malicious or spam
destinations before anyone clicks through.

**Stack:** Python 3.12 · FastAPI (async) · PostgreSQL + SQLAlchemy 2.0 (asyncpg) + Alembic · Redis · RabbitMQ
(aio-pika) · Kafka (aiokafka) · OAuth2 password flow + JWT · OpenAI / Hugging Face / Google Safe Browsing (all
optional) · Docker Compose · pytest

## Run everything
```bash
cp .env.example .env            # then set JWT_SECRET (required); API keys are optional
docker compose up --build       # API http://localhost:8000/docs · RabbitMQ UI http://localhost:15672
```

## Develop locally (infra in Docker, code on the host)
```bash
docker compose up -d postgres redis rabbitmq kafka
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload                 # API
.venv/bin/python -m worker.analysis_worker              # RabbitMQ consumer
.venv/bin/python -m worker.click_consumer               # Kafka consumer
.venv/bin/pytest -q                                     # 35 tests, no Docker needed (SQLite + fakeredis)
```
Host ports: Postgres 5433, Redis 6380, RabbitMQ 5672/15672, Kafka 9092.

## API (full schema at /docs; design in [docs/SmartUrl-api.md](docs/SmartUrl-api.md))
| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register` · `POST /auth/login` (access + refresh JWT) · `POST /auth/refresh` · `GET /auth/config` |
| Users | `GET/PATCH/DELETE /users/me` · `DELETE /users/me/resources` |
| Short URLs | `POST /shorten/` · `POST /shorten/batch` · `GET /urls/history` · `GET/DELETE /urls/{short_code}` · `GET /{short_code}` (redirect) |
| QR codes | `POST /qrcode/` · `GET /qrcode/{id}/image` (PNG on demand) · `GET /qrcode/{id}` (redirect) · `GET /qrcodes/history` · `DELETE /qrcode/{id}` |
| AI analysis | `GET /ai/analysis/url/{code}` · `GET /ai/analysis/qrcode/{id}` · `POST /ai/reanalyze/{type}/{id}` (202) |
| Analytics | `GET /analytics/url/{code}` · `GET /analytics/qrcode/{id}` (`granularity=day|week|month`) · `GET /analytics/summary` |

Data model: [docs/SmartUrl-database-schema.md](docs/SmartUrl-database-schema.md) — `users`, `urls`, `qrcodes`, `ai_analyses`, `analytics`.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and [bench/](bench/) for the load test.

## Hosted deployment (free tiers)
`render.yaml` deploys the API to Render's free plan with `EMBEDDED_WORKERS=true` (the RabbitMQ and Kafka consumers
run inside the API process, since free plans allow one process). Data services: Neon (PostgreSQL; its
`?sslmode=require` URL works as-is), Upstash (Redis, `rediss://`), CloudAMQP (RabbitMQ, `amqps://`), Aiven (Kafka
over SSL with client certificates — create the `link.clicks` topic). The UI deploys to Vercel with
`VITE_API_URL` pointing at the API.

Public-deployment safeguards: `REGISTRATION_INVITE_CODE` gates sign-up so the shortener cannot be used to mint
phishing redirects, and `DEMO_USERNAME`/`DEMO_PASSWORD` seed a **read-only** demo account (shown on the login page)
with sample links, so visitors can try it without registering.
