"""Kafka consumer: batches click events into PostgreSQL.

Reads up to BATCH events (or whatever arrived within 500 ms), writes them in one transaction, then commits
the Kafka offsets, so a crash replays at most one batch instead of losing clicks.
"""
import asyncio
import json
import logging
import os

from aiokafka import AIOKafkaConsumer

from app import db
from app.config import get_settings
from app.services import persist_clicks

BATCH = int(os.environ.get("CLICK_BATCH", "500"))
log = logging.getLogger("click_consumer")


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    consumer = AIOKafkaConsumer(s.clicks_topic, bootstrap_servers=s.kafka_bootstrap, group_id="click-writer",
                                enable_auto_commit=False, auto_offset_reset="earliest")
    await consumer.start()
    log.info("consuming %s", s.clicks_topic)
    try:
        while True:
            batches = await consumer.getmany(timeout_ms=500, max_records=BATCH)
            events = [json.loads(m.value) for msgs in batches.values() for m in msgs]
            if not events:
                continue
            async with db.SessionLocal() as session:
                await persist_clicks(session, events)
            await consumer.commit()
            log.info("stored %d click events", len(events))
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(main())
