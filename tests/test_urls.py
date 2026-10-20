async def test_shorten_analyzes_and_history(client, auth):
    r = await client.post("/shorten/", json={"target_url": "https://github.com/YanooLi"}, headers=auth)
    assert r.status_code == 201
    u = r.json()
    assert len(u["short_code"]) == 7 and u["short_url"].endswith("/" + u["short_code"]) and u["ai_analysis"] is None
    a = (await client.get(f"/ai/analysis/url/{u['short_code']}", headers=auth)).json()["analysis"]
    assert a["status"] == "done" and a["is_safe"] is True and a["safety_score"] >= 0.9
    assert a["category"] == "developer" and a["ai_provider"] == "rules"
    hist = (await client.get("/urls/history", headers=auth)).json()
    assert hist["total"] == 1 and hist["urls"][0]["ai_analysis"]["category"] == "developer"


async def test_ai_disabled_skips_classification(client, auth):
    u = (await client.post("/shorten/", json={"target_url": "https://www.youtube.com/", "ai_enabled": False}, headers=auth)).json()
    a = (await client.get(f"/ai/analysis/url/{u['short_code']}", headers=auth)).json()["analysis"]
    assert a["category"] is None and a["ai_provider"] is None and a["is_safe"] is True


async def test_custom_title_kept(client, auth):
    u = (await client.post("/shorten/", json={"target_url": "https://example.com/a", "title": "My Campaign Link"}, headers=auth)).json()
    assert u["title"] == "My Campaign Link"


async def test_pagination_and_sort(client, auth):
    r = await client.post("/shorten/batch", json={"target_urls": [f"https://example.com/p/{i}" for i in range(25)]}, headers=auth)
    assert r.status_code == 201 and len({u["short_code"] for u in r.json()}) == 25
    p1 = (await client.get("/urls/history?page=1&limit=10", headers=auth)).json()
    p3 = (await client.get("/urls/history?page=3&limit=10", headers=auth)).json()
    assert p1["total"] == 25 and len(p1["urls"]) == 10 and len(p3["urls"]) == 5
    asc = (await client.get("/urls/history?limit=100&order=asc", headers=auth)).json()["urls"]
    assert [x["created_at"] for x in asc] == sorted(x["created_at"] for x in asc)
    assert (await client.post("/shorten/batch", json={"target_urls": ["https://example.com"] * 101}, headers=auth)).status_code == 422


async def test_unsafe_link_flagged(client, auth):
    u = (await client.post("/shorten/", json={"target_url": "http://paypal-login.secure-verify.xyz/account/update"}, headers=auth)).json()
    a = (await client.get(f"/ai/analysis/url/{u['short_code']}", headers=auth)).json()["analysis"]
    assert a["is_safe"] is False and a["safety_score"] < 0.5 and "brand_impersonation" in a["threat_types"]
    assert any("paypal" in r for r in a["reasons"])


async def test_ownership_and_delete(client, auth):
    from tests.conftest import make_user
    u = (await client.post("/shorten/", json={"target_url": "https://example.com/mine"}, headers=auth)).json()
    other = {"Authorization": f"Bearer {(await make_user(client))['access_token']}"}
    assert (await client.get(f"/ai/analysis/url/{u['short_code']}", headers=other)).status_code == 404
    assert (await client.delete(f"/urls/{u['short_code']}", headers=other)).status_code == 404
    assert (await client.delete(f"/urls/{u['short_code']}", headers=auth)).status_code == 204
    assert (await client.get(f"/{u['short_code']}")).status_code == 404


async def test_reanalyze_queues(client, auth):
    u = (await client.post("/shorten/", json={"target_url": "https://example.com/r"}, headers=auth)).json()
    r = await client.post(f"/ai/reanalyze/url/{u['short_code']}", headers=auth)
    assert r.status_code == 202 and r.json()["message"] == "Re-analysis queued"


async def test_custom_alias(client, auth):
    r = await client.post("/shorten/", json={"target_url": "https://www.cmu.edu/", "custom_alias": "cmu-home"}, headers=auth)
    assert r.status_code == 201 and r.json()["short_code"] == "cmu-home" and r.json()["short_url"].endswith("/cmu-home")
    redirect = await client.get("/cmu-home")
    assert redirect.status_code in (302, 307) and redirect.headers["location"] == "https://www.cmu.edu/"
    # taken (case-insensitively), reserved, or malformed aliases are refused
    dup = await client.post("/shorten/", json={"target_url": "https://example.com", "custom_alias": "CMU-Home"}, headers=auth)
    assert dup.status_code == 409 and "taken" in dup.json()["detail"]
    reserved = await client.post("/shorten/", json={"target_url": "https://example.com", "custom_alias": "docs"}, headers=auth)
    assert reserved.status_code == 409 and "reserved" in reserved.json()["detail"]
    for bad in ("-lead", "trail-", "has space", "slash/es", "a" * 33, "emoji😀"):
        assert (await client.post("/shorten/", json={"target_url": "https://example.com", "custom_alias": bad},
                                  headers=auth)).status_code == 422, bad
