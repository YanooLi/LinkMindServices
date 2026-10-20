async def test_create_analyzes_and_lists(client, auth):
    r = await client.post("/api/links", json={"url": "https://github.com/YanooLi"}, headers=auth)
    assert r.status_code == 201
    link = r.json()
    assert len(link["short_code"]) == 7 and link["short_url"].endswith(link["short_code"])
    got = (await client.get(f"/api/links/{link['id']}", headers=auth)).json()
    assert got["status"] == "done" and got["risk_level"] == "safe"
    assert got["category"] == "developer" and got["category_source"] == "rules"
    page = (await client.get("/api/links", headers=auth)).json()
    assert [l["id"] for l in page["items"]] == [link["id"]] and page["next_cursor"] is None


async def test_alias_conflict_and_ownership(client, auth):
    r = await client.post("/api/links", json={"url": "https://example.com", "alias": "my-alias"}, headers=auth)
    assert r.status_code == 201 and r.json()["short_code"] == "my-alias"
    again = await client.post("/api/links", json={"url": "https://example.org", "alias": "my-alias"}, headers=auth)
    assert again.status_code == 409
    other = await client.post("/api/auth/register", json={"email": "other@example.com", "password": "longenough"})
    tok = (await client.post("/api/auth/token", data={"username": "other@example.com", "password": "longenough"})).json()
    hdr = {"Authorization": f"Bearer {tok['access_token']}"}
    assert other.status_code == 201
    assert (await client.get(f"/api/links/{r.json()['id']}", headers=hdr)).status_code == 404


async def test_batch_and_cursor_pagination(client, auth):
    urls = [f"https://example.com/page/{i}" for i in range(25)]
    r = await client.post("/api/links/batch", json={"urls": urls}, headers=auth)
    assert r.status_code == 201 and r.json()["queued_for_analysis"] == 25
    assert len({l["short_code"] for l in r.json()["created"]}) == 25
    first = (await client.get("/api/links?limit=10", headers=auth)).json()
    second = (await client.get(f"/api/links?limit=10&cursor={first['next_cursor']}", headers=auth)).json()
    third = (await client.get(f"/api/links?limit=10&cursor={second['next_cursor']}", headers=auth)).json()
    ids = [l["id"] for p in (first, second, third) for l in p["items"]]
    assert len(ids) == 25 == len(set(ids)) and ids == sorted(ids, reverse=True)
    assert third["next_cursor"] is None


async def test_batch_limit(client, auth):
    r = await client.post("/api/links/batch", json={"urls": ["https://example.com"] * 101}, headers=auth)
    assert r.status_code == 422


async def test_suspicious_link_flagged(client, auth):
    r = await client.post("/api/links", json={"url": "http://paypal-login.secure-verify.xyz/account/update"}, headers=auth)
    got = (await client.get(f"/api/links/{r.json()['id']}", headers=auth)).json()
    assert got["risk_level"] == "suspicious"
    assert any("paypal" in reason for reason in got["risk_reasons"])


async def test_delete(client, auth):
    r = await client.post("/api/links", json={"url": "https://example.com/x"}, headers=auth)
    assert (await client.delete(f"/api/links/{r.json()['id']}", headers=auth)).status_code == 204
    assert (await client.get(f"/api/links/{r.json()['id']}", headers=auth)).status_code == 404
