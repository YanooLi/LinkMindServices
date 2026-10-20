"""Redis: cache-aside for short-code lookups on the redirect hot path, plus a fixed-window rate limiter."""
import json
import time

from fastapi import HTTPException, Request
from redis.asyncio import Redis

from app.config import get_settings

_redis: Redis | None = None


def set_redis(client: Redis | None) -> None:
    global _redis
    _redis = client


def get_redis() -> Redis | None:
    return _redis


def _key(code: str) -> str:
    return f"link:{code}"


async def get_cached_link(code: str) -> dict | None:
    if _redis is None or not get_settings().cache_enabled:
        return None
    raw = await _redis.get(_key(code))
    return json.loads(raw) if raw else None


async def cache_link(code: str, data: dict) -> None:
    if _redis is None or not get_settings().cache_enabled:
        return
    await _redis.set(_key(code), json.dumps(data), ex=get_settings().cache_ttl_seconds)


async def invalidate_link(code: str) -> None:
    if _redis is not None:
        await _redis.delete(_key(code))


async def rate_limit(request: Request, bucket: str, identity: str) -> None:
    """Allow rate_limit_per_minute calls per identity per minute; 429 with Retry-After beyond that."""
    if _redis is None:
        return
    limit = get_settings().rate_limit_per_minute
    window = int(time.time() // 60)
    key = f"rl:{bucket}:{identity}:{window}"
    count = await _redis.incr(key)
    if count == 1:
        await _redis.expire(key, 61)
    if count > limit:
        retry = 60 - int(time.time() % 60)
        raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(retry)})
