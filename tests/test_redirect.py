from app.config import get_settings


async def test_redirect_caches_and_counts_clicks(client, auth, redis):
    link = (await client.post("/api/links", json={"url": "https://example.com/target"}, headers=auth)).json()
    code = link["short_code"]
    r = await client.get(f"/r/{code}", headers={"referer": "https://news.ycombinator.com/"})
    assert r.status_code == 307 and r.headers["location"] == "https://example.com/target"
    assert await redis.get(f"link:{code}") is not None          # cache-aside filled on first lookup
    await client.get(f"/r/{code}")
    stats = (await client.get(f"/api/links/{link['id']}/stats", headers=auth)).json()
    assert stats["total_clicks"] == 2 and sum(d["clicks"] for d in stats["daily"]) == 2
    assert {"referrer": "https://news.ycombinator.com/", "clicks": 1} in stats["top_referrers"]


async def test_delete_invalidates_cache(client, auth, redis):
    link = (await client.post("/api/links", json={"url": "https://example.com/gone"}, headers=auth)).json()
    await client.get(f"/r/{link['short_code']}")
    await client.delete(f"/api/links/{link['id']}", headers=auth)
    assert await redis.get(f"link:{link['short_code']}") is None
    assert (await client.get(f"/r/{link['short_code']}")).status_code == 404


async def test_suspicious_interstitial_then_confirm(client, auth):
    link = (await client.post("/api/links", json={"url": "http://203.0.113.9/login"}, headers=auth)).json()
    warn = await client.get(f"/r/{link['short_code']}")
    assert warn.status_code == 200 and "suspicious" in warn.text
    assert (await client.get(f"/r/{link['short_code']}?confirm=1")).status_code == 307


async def test_cache_disabled_still_works(client, auth, redis, monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_enabled", False)
    link = (await client.post("/api/links", json={"url": "https://example.com/nc"}, headers=auth)).json()
    assert (await client.get(f"/r/{link['short_code']}")).status_code == 307
    assert await redis.get(f"link:{link['short_code']}") is None


async def test_rate_limit(client, auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 2)
    for _ in range(2):
        assert (await client.post("/api/links", json={"url": "https://example.com"}, headers=auth)).status_code == 201
    r = await client.post("/api/links", json={"url": "https://example.com"}, headers=auth)
    assert r.status_code == 429 and "retry-after" in r.headers
