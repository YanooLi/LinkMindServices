from app.config import get_settings

DESKTOP = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"


async def test_redirect_cache_and_analytics(client, auth, redis):
    u = (await client.post("/shorten/", json={"target_url": "https://example.com/target"}, headers=auth)).json()
    code = u["short_code"]
    r = await client.get(f"/{code}", headers={"referer": "https://www.linkedin.com/feed/", "user-agent": DESKTOP,
                                              "x-forwarded-for": "8.8.8.8"})
    assert r.status_code == 307 and r.headers["location"] == "https://example.com/target"
    assert await redis.get(f"url:{code}") is not None
    await client.get(f"/{code}", headers={"user-agent": "Mozilla/5.0 (iPad; CPU OS 17_0) Mobile"})
    a = (await client.get(f"/analytics/url/{code}", headers=auth)).json()
    assert a["clicks"] == 2 and sum(d["clicks"] for d in a["click_data"]["daily"]) == 2
    assert {"type": "desktop", "count": 1} in a["click_data"]["devices"] and {"type": "tablet", "count": 1} in a["click_data"]["devices"]
    assert {"country": "United States", "count": 1} in a["click_data"]["countries"]
    assert {"referrer": "linkedin.com", "count": 1} in a["click_data"]["referrers"]
    weekly = (await client.get(f"/analytics/url/{code}?granularity=week", headers=auth)).json()
    assert sum(d["clicks"] for d in weekly["click_data"]["daily"]) == 2


async def test_unsafe_redirect_blocked(client, auth):
    u = (await client.post("/shorten/", json={"target_url": "http://203.0.113.9/login"}, headers=auth)).json()
    r = await client.get(f"/{u['short_code']}")
    assert r.status_code == 403 and "blocked" in r.text


async def test_delete_invalidates_cache(client, auth, redis):
    u = (await client.post("/shorten/", json={"target_url": "https://example.com/gone"}, headers=auth)).json()
    await client.get(f"/{u['short_code']}")
    await client.delete(f"/urls/{u['short_code']}", headers=auth)
    assert await redis.get(f"url:{u['short_code']}") is None
    assert (await client.get(f"/{u['short_code']}")).status_code == 404


async def test_reserved_paths_not_shadowed(client):
    assert (await client.get("/health")).status_code == 200
    assert (await client.get("/docs")).status_code == 200


async def test_cache_disabled_still_works(client, auth, redis, monkeypatch):
    monkeypatch.setattr(get_settings(), "cache_enabled", False)
    u = (await client.post("/shorten/", json={"target_url": "https://example.com/nc"}, headers=auth)).json()
    assert (await client.get(f"/{u['short_code']}")).status_code == 307
    assert await redis.get(f"url:{u['short_code']}") is None


async def test_rate_limit(client, auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "rate_limit_per_minute", 2)
    for _ in range(2):
        assert (await client.post("/shorten/", json={"target_url": "https://example.com"}, headers=auth)).status_code == 201
    r = await client.post("/shorten/", json={"target_url": "https://example.com"}, headers=auth)
    assert r.status_code == 429 and "retry-after" in r.headers


async def test_summary(client, auth):
    u = (await client.post("/shorten/", json={"target_url": "https://example.com/s"}, headers=auth)).json()
    q = (await client.post("/qrcode/", json={"target_url": "https://example.com/q"}, headers=auth)).json()
    await client.get(f"/{u['short_code']}")
    await client.get(f"/qrcode/{q['qr_code_id']}")
    s = (await client.get("/analytics/summary?period=week", headers=auth)).json()
    assert s["total_urls"] == 1 and s["total_qrcodes"] == 1 and s["total_clicks"] == 1 and s["total_qr_scans"] == 1
    assert len(s["daily_activity"]) == 7 and s["top_urls"][0]["short_code"] == u["short_code"]
