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
.venv/bin/pytest -q                                     # 25 tests, no Docker needed (SQLite + fakeredis)
```
Host ports: Postgres 5433, Redis 6380, RabbitMQ 5672/15672, Kafka 9092.

## API (full schema at /docs)
| Method | Path | |
|---|---|---|
| POST | /api/auth/register · /api/auth/token · GET /api/auth/me | accounts, OAuth2 password flow → JWT |
| POST | /api/links | shorten one URL (optional custom alias) |
| POST | /api/links/batch | shorten up to 100 URLs in one transaction |
| GET | /api/links?cursor=&risk=&q= | keyset-paginated list with filters |
| GET/DELETE | /api/links/{id} | one link |
| POST | /api/links/{id}/reanalyze | queue a fresh analysis |
| GET | /api/links/{id}/stats | daily clicks + top referrers |
| GET | /r/{code} | redirect (warning page for suspicious, 403 for malicious) |

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and [bench/](bench/) for the load test.
