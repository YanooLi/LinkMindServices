from tests.conftest import make_user


async def test_register_login_refresh_profile(client):
    r = await client.post("/auth/register", json={"username": "johndoe", "email": "John@Example.com", "password": "securepassword123"})
    assert r.status_code == 201 and r.json()["email"] == "john@example.com" and r.json()["username"] == "johndoe"
    dup = await client.post("/auth/register", json={"username": "johndoe", "email": "other@example.com", "password": "securepassword123"})
    assert dup.status_code == 409
    assert (await client.post("/auth/login", json={"username": "johndoe", "password": "wrong-pass"})).status_code == 401
    tok = (await client.post("/auth/login", json={"username": "john@example.com", "password": "securepassword123"})).json()
    assert tok["token_type"] == "bearer" and tok["expires_in"] == 3600 and tok["user"]["username"] == "johndoe"
    me = (await client.get("/users/me", headers={"Authorization": f"Bearer {tok['access_token']}"})).json()
    assert me["stats"] == {"urls_created": 0, "qr_codes_created": 0}
    fresh = await client.post("/auth/refresh", json={"refresh_token": tok["refresh_token"]})
    assert fresh.status_code == 200 and fresh.json()["access_token"]
    # a refresh token is not an access token, and vice versa
    assert (await client.get("/users/me", headers={"Authorization": f"Bearer {tok['refresh_token']}"})).status_code == 401
    assert (await client.post("/auth/refresh", json={"refresh_token": tok["access_token"]})).status_code == 401


async def test_profile_update_and_conflicts(client):
    a, b = await make_user(client), await make_user(client)
    h = {"Authorization": f"Bearer {a['access_token']}"}
    r = await client.patch("/users/me", json={"first_name": "Alex", "bio": "Link curator"}, headers=h)
    assert r.status_code == 200 and r.json()["first_name"] == "Alex"
    clash = await client.patch("/users/me", json={"username": b["user"]["username"]}, headers=h)
    assert clash.status_code == 409


async def test_requires_auth_and_valid_input(client):
    assert (await client.get("/users/me")).status_code == 401
    assert (await client.get("/users/me", headers={"Authorization": "Bearer nope"})).status_code == 401
    bad = await client.post("/auth/register", json={"username": "x", "email": "b@example.com", "password": "short"})
    assert bad.status_code == 422
