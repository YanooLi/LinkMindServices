"""RabbitMQ consumer: runs link analysis jobs. Scale out by starting more processes (docker compose --scale).

Each process handles up to PREFETCH messages concurrently; a message is acked only after its analysis is
committed, so a crashed worker's jobs are redelivered. In a hosted deployment the same consumer can run inside
the API process instead (EMBEDDED_WORKERS=true, see app/main.py).
"""
import asyncio
import json
import logging
import os

import aio_pika
from redis.asyncio import Redis

from app import cache, db
from app.analysis.analyzer import analyze_resource
from app.config import get_settings

PREFETCH = int(os.environ.get("WORKER_PREFETCH", "8"))
log = logging.getLogger("analysis_worker")


async def handle(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    async with message.process(requeue=False):
        job = json.loads(message.body)
        async with db.SessionLocal() as session:
            row = await analyze_resource(session, job["resource_type"], job["resource_id"])
        log.info("analyzed %s %s -> %s", job["resource_type"], job["resource_id"],
                 f"score {row.safety_score}, safe={row.is_safe}" if row else "missing")


async def start_consumer() -> aio_pika.abc.AbstractRobustConnection:
    """Connect and start consuming; returns the connection so the caller can close it."""
    s = get_settings()
    conn = await aio_pika.connect_robust(s.rabbitmq_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=PREFETCH)
    queue = await channel.declare_queue(s.analysis_queue, durable=True)
    await queue.consume(handle)
    log.info("waiting for analysis jobs on %s (prefetch=%d)", s.analysis_queue, PREFETCH)
    return conn


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    cache.set_redis(Redis.from_url(get_settings().redis_url, decode_responses=True))
    await start_consumer()
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
