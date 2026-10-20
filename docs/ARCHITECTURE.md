# LinkMind architecture

```
 React UI ──REST/JWT──▶ FastAPI ──▶ PostgreSQL (users, links, click_events; Alembic migrations)
                          │  ▲
            create/batch  │  │ cache-aside on /r/{code}
                          ▼  │
                     RabbitMQ   Redis (link:{code} → url + risk, TTL 1 h; rate-limit counters)
                          │
                          ▼
              analysis worker(s) ── heuristics → Google Safe Browsing → fetch <title> (SSRF-safe)
                                    → OpenAI | Hugging Face zero-shot | keyword rules → UPDATE link,
                                      invalidate cache
   /r/{code} ──click event──▶ Kafka topic link.clicks ──▶ click consumer: batch INSERT + counters
```

## Key decisions (and why)
- **Redirect hot path = Redis cache-aside.** The redirect only needs `url` and `risk`; they are cached per short
  code with a TTL and invalidated whenever analysis or deletion changes them. Measured effect: see below.
- **Two brokers for two jobs.** RabbitMQ is a *work queue*: each analysis job must be done once, by any worker,
  and redelivered if a worker dies (ack after commit, prefetch 8). Kafka is an *event log*: clicks are appended
  and consumed in batches (≤ 500 per transaction, offsets committed after the write), so traffic spikes never
  wait on the database and a crash replays at most one batch.
- **Analysis is asynchronous.** Fetching a page and calling an AI API can take seconds, so creating a link returns
  immediately with `status: pending`; the UI polls only while something is pending.
- **Graceful degradation.** Without API keys analysis falls back to rules; without RabbitMQ/Kafka the API does the
  work in-process. This is also what the test suite exercises (SQLite + fakeredis, no Docker).
- **Security.** bcrypt password hashes; JWT bearer tokens; per-user/IP Redis rate limits (429 + Retry-After);
  the page fetcher refuses non-http(s) schemes and any host resolving to a private, loopback or link-local
  address on every redirect hop (SSRF), with a 5 s timeout and 256 KB cap; HTML on warning pages is escaped.
- **Keyset pagination** (`id < cursor`) instead of OFFSET, backed by an `(owner_id, created_at)` index.

## Risk model
`app/analysis/heuristics.py`: raw-IP hosts, `@` in the authority, punycode, brand names on non-brand domains,
abuse-heavy TLDs, deep subdomains, nested shorteners, credential words in the path. One high-signal reason or two
others → `suspicious`; a Google Safe Browsing match → `malicious` (redirect blocked with 403). Suspicious links get
an interstitial with "Continue anyway".

## Measured (bench/loadtest.py, results in bench/results.json)
2026-10-19, MacBook (Apple Silicon), everything local, **one** uvicorn process, 50 concurrent clients, 1,000 links,
20 s per run; both runs include the Kafka publish on every redirect:

| | cache off | cache on |
|---|---|---|
| p50 latency | 87.7 ms | 55.0 ms (−37%) |
| p95 latency | 472.9 ms | 270.6 ms (−43%) |
| throughput | 349 req/s | 572 req/s (1.64×) |

Not yet measured: detection accuracy against a labelled URL set (planned: PhishTank / OpenPhish samples vs a
benign list).
