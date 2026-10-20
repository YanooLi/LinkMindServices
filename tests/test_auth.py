async def test_register_login_me(client):
    r = await client.post("/api/auth/register", json={"email": "A@Example.com", "password": "longenough"})
    assert r.status_code == 201 and r.json()["email"] == "a@example.com"
    assert (await client.post("/api/auth/register", json={"email": "a@example.com", "password": "longenough"})).status_code == 409
    bad = await client.post("/api/auth/token", data={"username": "a@example.com", "password": "wrong-pass"})
    assert bad.status_code == 401
    tok = (await client.post("/api/auth/token", data={"username": "a@example.com", "password": "longenough"})).json()
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok['access_token']}"})
    assert me.status_code == 200 and me.json()["email"] == "a@example.com"


async def test_rejects_bad_token_and_short_password(client):
    assert (await client.get("/api/auth/me", headers={"Authorization": "Bearer nope"})).status_code == 401
    assert (await client.post("/api/auth/register", json={"email": "b@example.com", "password": "short"})).status_code == 422
