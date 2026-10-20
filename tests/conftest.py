"""Tests run without Docker: SQLite (aiosqlite) instead of PostgreSQL, fakeredis instead of Redis, and the
brokers switched off so analysis and click writes take the in-process fallback paths."""
import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(), "test.db")
os.environ.update({
    "DATABASE_URL": f"sqlite+aiosqlite:///{_db}",
    "RABBITMQ_ENABLED": "false", "KAFKA_ENABLED": "false",
    "FETCH_PAGE_METADATA": "false", "OPENAI_API_KEY": "", "HUGGINGFACE_TOKEN": "", "SAFE_BROWSING_API_KEY": "",
    "RATE_LIMIT_PER_MINUTE": "1000", "JWT_SECRET": "test-secret-" + "x" * 32,
})

import pytest  # noqa: E402
from fakeredis import aioredis  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import cache, db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    async with db.engine.begin() as conn:
        await conn.run_sync(db.Base.metadata.create_all)
    yield
    await db.engine.dispose()


@pytest.fixture(autouse=True)
async def redis():
    r = aioredis.FakeRedis(decode_responses=True)
    cache.set_redis(r)
    yield r
    await r.flushall()


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


_counter = iter(range(10_000))


async def make_user(client, password="correct-horse"):
    n = next(_counter)
    r = await client.post("/auth/register", json={"username": f"user{n}", "email": f"user{n}@example.com", "password": password})
    assert r.status_code == 201, r.text
    r = await client.post("/auth/login", json={"username": f"user{n}", "password": password})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
async def auth(client):
    return {"Authorization": f"Bearer {(await make_user(client))['access_token']}"}
