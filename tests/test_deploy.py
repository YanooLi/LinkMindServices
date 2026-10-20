from app import demo
from app.config import get_settings
from app.db import normalize_url


async def test_invite_code_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "registration_invite_code", "let-me-in")
    body = {"username": "invited", "email": "invited@example.com", "password": "longenough"}
    assert (await client.post("/auth/register", json=body)).status_code == 403
    assert (await client.post("/auth/register", json={**body, "invite_code": "wrong"})).status_code == 403
    assert (await client.post("/auth/register", json={**body, "invite_code": "let-me-in"})).status_code == 201
    assert (await client.get("/auth/config")).json()["registration_requires_invite"] is True


async def test_demo_account_is_seeded_and_read_only(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_username", "demo")
    monkeypatch.setattr(get_settings(), "demo_password", "demo-password-123")
    items = await demo.seed_demo()
    assert len(items) == len(demo.SAMPLE_URLS) + 1
    assert await demo.seed_demo() == []                         # idempotent
    tok = (await client.post("/auth/login", json={"username": "demo", "password": "demo-password-123"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    urls = (await client.get("/urls/history", headers=h)).json()["urls"]
    assert len(urls) == len(demo.SAMPLE_URLS)
    assert (await client.post("/shorten/", json={"target_url": "https://example.com"}, headers=h)).status_code == 403
    assert (await client.post("/qrcode/", json={"target_url": "https://example.com"}, headers=h)).status_code == 403
    assert (await client.delete(f"/urls/{urls[0]['short_code']}", headers=h)).status_code == 403
    assert (await client.patch("/users/me", json={"bio": "x"}, headers=h)).status_code == 403
    assert (await client.delete("/users/me/resources", headers=h)).status_code == 403
    assert (await client.get(f"/analytics/url/{urls[0]['short_code']}", headers=h)).status_code == 200


async def test_delete_all_resources_and_account(client, auth):
    await client.post("/shorten/", json={"target_url": "https://example.com/1"}, headers=auth)
    await client.post("/qrcode/", json={"target_url": "https://example.com/2"}, headers=auth)
    assert (await client.delete("/users/me/resources", headers=auth)).status_code == 204
    me = (await client.get("/users/me", headers=auth)).json()
    assert me["stats"] == {"urls_created": 0, "qr_codes_created": 0}
    assert (await client.delete("/users/me", headers=auth)).status_code == 204
    assert (await client.get("/users/me", headers=auth)).status_code == 401


def test_provider_database_urls():
    assert normalize_url("postgres://u:p@h/db?sslmode=require&channel_binding=require") == \
        ("postgresql+asyncpg://u:p@h/db", {"ssl": "require"})
