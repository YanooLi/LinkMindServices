from app import demo
from app.config import get_settings
from app.db import normalize_url


async def test_invite_code_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "registration_invite_code", "let-me-in")
    body = {"email": "invited@example.com", "password": "longenough"}
    assert (await client.post("/api/auth/register", json=body)).status_code == 403
    assert (await client.post("/api/auth/register", json={**body, "invite_code": "wrong"})).status_code == 403
    assert (await client.post("/api/auth/register", json={**body, "invite_code": "let-me-in"})).status_code == 201
    cfg = (await client.get("/api/auth/config")).json()
    assert cfg["registration_requires_invite"] is True


async def test_demo_account_is_seeded_and_read_only(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "demo_email", "demo@linkmind.dev")
    monkeypatch.setattr(get_settings(), "demo_password", "demo-password-123")
    ids = await demo.seed_demo()
    assert len(ids) == len(demo.SAMPLE_URLS)
    assert await demo.seed_demo() == []                        # idempotent
    cfg = (await client.get("/api/auth/config")).json()
    assert cfg["demo_email"] == "demo@linkmind.dev"
    tok = (await client.post("/api/auth/token", data={"username": "demo@linkmind.dev",
                                                      "password": "demo-password-123"})).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    links = (await client.get("/api/links", headers=h)).json()["items"]
    assert len(links) == len(demo.SAMPLE_URLS)
    assert (await client.post("/api/links", json={"url": "https://example.com"}, headers=h)).status_code == 403
    assert (await client.post("/api/links/batch", json={"urls": ["https://example.com"]}, headers=h)).status_code == 403
    assert (await client.delete(f"/api/links/{links[0]['id']}", headers=h)).status_code == 403
    assert (await client.get(f"/api/links/{links[0]['id']}/stats", headers=h)).status_code == 200


async def test_public_config_without_demo(client):
    cfg = (await client.get("/api/auth/config")).json()
    assert cfg == {"registration_requires_invite": False, "demo_email": None, "demo_password": None}


def test_provider_database_urls():
    assert normalize_url("postgres://u:p@h/db?sslmode=require&channel_binding=require") == \
        ("postgresql+asyncpg://u:p@h/db", {"ssl": "require"})
    assert normalize_url("postgresql+asyncpg://u:p@localhost:5433/db") == ("postgresql+asyncpg://u:p@localhost:5433/db", {})
