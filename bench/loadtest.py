"""Measure the redirect hot path: latency percentiles and throughput at a fixed concurrency.

Usage:
  python bench/loadtest.py setup  --links 1000                 # creates a bench user + links, saves codes
  python bench/loadtest.py run --label cache-on  --seconds 20 --concurrency 50
  (restart the API with CACHE_ENABLED=false)
  python bench/loadtest.py run --label cache-off --seconds 20 --concurrency 50
  python bench/loadtest.py compare

Results are appended to bench/results.json with the machine and settings, so any number quoted elsewhere
can be traced back to the run that produced it.
"""
import argparse
import asyncio
import json
import os
import platform
import random
import statistics
import time
from datetime import datetime, timezone

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
CODES = os.path.join(HERE, "codes.json")
RESULTS = os.path.join(HERE, "results.json")


async def setup(base: str, n: int) -> None:
    async with httpx.AsyncClient(base_url=base, timeout=30) as c:
        user, pw = "bench", "bench-password"
        await c.post("/auth/register", json={"username": user, "email": "bench@example.com", "password": pw})
        tok = (await c.post("/auth/login", json={"username": user, "password": pw})).json()["access_token"]
        h = {"Authorization": f"Bearer {tok}"}
        codes = []
        for i in range(0, n, 100):
            urls = [f"https://example.com/bench/{j}" for j in range(i, min(n, i + 100))]
            r = await c.post("/shorten/batch", json={"target_urls": urls}, headers=h)
            r.raise_for_status()
            codes += [l["short_code"] for l in r.json()]
    json.dump(codes, open(CODES, "w"))
    print(f"created {len(codes)} links -> {CODES}")


async def run(base: str, label: str, seconds: float, concurrency: int) -> None:
    codes = json.load(open(CODES))
    lat: list[float] = []
    errors = 0
    stop = time.perf_counter() + seconds
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)

    async def worker(c: httpx.AsyncClient):
        nonlocal errors
        while time.perf_counter() < stop:
            t0 = time.perf_counter()
            try:
                r = await c.get(f"/{random.choice(codes)}")
                if r.status_code != 307:
                    errors += 1
                    continue
            except httpx.HTTPError:
                errors += 1
                continue
            lat.append((time.perf_counter() - t0) * 1000)

    async with httpx.AsyncClient(base_url=base, timeout=10, limits=limits, follow_redirects=False) as c:
        for _ in range(200):                      # warm-up (fills the cache when it is on)
            await c.get(f"/{random.choice(codes)}")
        t0 = time.perf_counter()
        await asyncio.gather(*(worker(c) for _ in range(concurrency)))
        elapsed = time.perf_counter() - t0
    q = statistics.quantiles(lat, n=100)
    res = {"label": label, "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "machine": f"{platform.system()} {platform.machine()} ({os.cpu_count()} cpu)",
           "concurrency": concurrency, "seconds": round(elapsed, 1), "requests": len(lat), "errors": errors,
           "rps": round(len(lat) / elapsed, 1), "p50_ms": round(q[49], 2), "p95_ms": round(q[94], 2),
           "p99_ms": round(q[98], 2), "mean_ms": round(statistics.fmean(lat), 2), "links": len(codes)}
    hist = json.load(open(RESULTS)) if os.path.exists(RESULTS) else []
    hist.append(res)
    json.dump(hist, open(RESULTS, "w"), indent=1)
    print(json.dumps(res, indent=1))


def compare() -> None:
    hist = json.load(open(RESULTS))
    on = next(r for r in reversed(hist) if r["label"].startswith("cache-on"))
    off = next(r for r in reversed(hist) if r["label"].startswith("cache-off"))
    for k in ("p50_ms", "p95_ms", "mean_ms"):
        print(f"{k:8} cache-off {off[k]:8} -> cache-on {on[k]:8}  ({(1 - on[k] / off[k]) * 100:.0f}% lower)")
    print(f"rps      cache-off {off['rps']:8} -> cache-on {on['rps']:8}  ({on['rps'] / off['rps']:.2f}x)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["setup", "run", "compare"])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--links", type=int, default=1000)
    ap.add_argument("--label", default="run")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--concurrency", type=int, default=50)
    a = ap.parse_args()
    if a.cmd == "setup":
        asyncio.run(setup(a.base, a.links))
    elif a.cmd == "run":
        asyncio.run(run(a.base, a.label, a.seconds, a.concurrency))
    else:
        compare()
