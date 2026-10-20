import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app import cache
from app.config import get_settings
from app.demo import seed_and_analyze
from app.messaging import analysis_publisher, click_publisher
from app.routers import auth, links, redirect

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if cache.get_redis() is None:
        cache.set_redis(Redis.from_url(s.redis_url, decode_responses=True))
    await analysis_publisher.start()
    await click_publisher.start()
    background: list[asyncio.Task] = []
    rabbit_conn = None
    if s.embedded_workers:
        # Free hosting tiers run one web process and no separate workers, so the consumers live here.
        from worker import analysis_worker, click_consumer

        if analysis_publisher.enabled:
            rabbit_conn = await analysis_worker.start_consumer()
        if click_publisher.enabled:
            background.append(asyncio.create_task(click_consumer.run()))
    background.append(asyncio.create_task(seed_and_analyze()))
    yield
    for task in background:
        task.cancel()
    if rabbit_conn is not None:
        await rabbit_conn.close()
    await analysis_publisher.stop()
    await click_publisher.stop()


app = FastAPI(title="LinkMind API", version="1.0.0", lifespan=lifespan,
              description="Short links with AI-assisted classification and malicious-URL detection.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth.router)
app.include_router(links.router)
app.include_router(redirect.router)


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "rabbitmq": analysis_publisher.enabled, "kafka": click_publisher.enabled,
            "cache": get_settings().cache_enabled}
