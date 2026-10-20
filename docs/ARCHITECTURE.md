# LinkMind architecture

Design sources: [SmartUrl-api.md](SmartUrl-api.md) (endpoints) and [SmartUrl-database-schema.md](SmartUrl-database-schema.md)
(tables). UI: the Figma Make design in the LinkMind-UI repo.

```
 React UI ──REST/JWT──▶ FastAPI ──▶ PostgreSQL: users · urls · qrcodes · ai_analyses · analytics (Alembic)
                          │  ▲
       create / batch     │  │ cache-aside on GET /{code} and GET /qrcode/{id}
                          ▼  │
                     RabbitMQ   Redis  (url:{code} / qrcode:{id} → destination + is_safe, TTL 1 h; rate limits)
                          │
                          ▼
              analysis worker(s): Google Safe Browsing → URL heuristics → SSRF-safe <title> fetch
                                  → optional AI category (OpenAI | Hugging Face zero-shot | rules)
                                  → composite safety score 0–1 → ai_analyses row, resource.is_safe, cache invalidated
   redirect ──visit event (ip, user agent, referer)──▶ Kafka "link.clicks" ──▶ consumer: device type, country (offline
                                                                               GeoIP), referrer host → analytics rows
```

## Key decisions
- **Redirect hot path does almost nothing.** Look up `{url, is_safe}` in Redis (cache-aside, invalidated after every
  analysis or delete), append one raw event to Kafka, return 307. Device type, country and referrer are derived by the
  consumer, not in the request — moving that work off the request path is what took cache-on throughput from 1.39×
  to 1.87× the cache-off baseline (see below).
- **Two brokers for two jobs.** RabbitMQ is a work queue (each analysis done once by any worker, acked after commit,
  redelivered on crash). Kafka is an event log (visits appended, consumed in batches of ≤ 500 per transaction, offsets
  committed after the write).
- **Safety score.** Starts at 1.0; Safe Browsing match → 0; each heuristic signal subtracts a weight (raw-IP host,
  `@` in the host, punycode, brand impersonation ≈ 0.55–0.6; suspicious TLD, deep subdomains, nested shortener,
  credential words 0.15–0.2; long URL / http 0.05); a "spam" AI label subtracts 0.3. Below 0.5 → `is_safe = false`
  and the redirect returns 403 with the reasons. Analysis is asynchronous, so a brand-new link redirects normally
  until its analysis is stored.
- **AI is optional per link** (`ai_enabled`, the "Enable AI Analysis" toggle): safety checks always run; the category
  classifier runs only when enabled. Without API keys the rules classifier is used, and `ai_provider` says which ran.
- **Privacy.** The visitor IP is used once by the consumer for an offline country lookup (geoip2fast) and never stored.
- **Security.** bcrypt; short-lived access JWT (1 h) + refresh JWT (7 d) with a `type` claim so one cannot be used as
  the other; per-IP/per-user Redis rate limits (429 + Retry-After); SSRF guard on the title fetcher (http(s) only, public
  IPs on every redirect hop, 5 s timeout, 256 KB cap) — note the DNS-rebinding gap: the host is resolved for the check and
  again by the HTTP client; invite-gated sign-up and a read-only demo account for public deployments.
- **QR images are generated on demand** (never stored) in the saved color and module style, and encode the tracked
  `/qrcode/{id}` URL so every scan is counted.

## Measured (bench/loadtest.py, raw runs in bench/results.json)
2026-10-20, MacBook (Apple Silicon, 10 CPU), everything local, one uvicorn process, 50 concurrent clients, 1,000 short
links, 20 s per run; every redirect publishes its visit event to Kafka in both configurations:

| | cache off | cache on |
|---|---|---|
| p50 latency | 77.3 ms | 48.7 ms (−37%) |
| p95 latency | 415.1 ms | 191.9 ms (−54%) |
| throughput | 394 req/s | 737 req/s (1.87×) |

Not yet measured: detection accuracy against a labelled URL set.
