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


def _key(resource_type: str, resource_id: str) -> str:
    return f"{resource_type}:{resource_id}"


async def get_cached(resource_type: str, resource_id: str) -> dict | None:
    """Hot-link cache for the redirect path (url or qrcode → destination + safety)."""
    if _redis is None or not get_settings().cache_enabled:
        return None
    raw = await _redis.get(_key(resource_type, resource_id))
    return json.loads(raw) if raw else None


async def set_cached(resource_type: str, resource_id: str, data: dict) -> None:
    if _redis is None or not get_settings().cache_enabled:
        return
    await _redis.set(_key(resource_type, resource_id), json.dumps(data), ex=get_settings().cache_ttl_seconds)


async def invalidate(resource_type: str, resource_id: str) -> None:
    if _redis is not None:
        await _redis.delete(_key(resource_type, resource_id))


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
