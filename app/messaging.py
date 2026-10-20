"""Message brokers.

* RabbitMQ (aio-pika): work queue of link-analysis jobs, consumed by worker/analysis_worker.py. Batch creation
  publishes one message per link so analysis scales with the number of worker processes, not API requests.
* Kafka (aiokafka): append-only stream of click events, consumed by worker/click_consumer.py, which writes them
  in batches. The redirect path only appends to the log, so a burst of clicks never waits on the database.

When a broker is disabled (tests, a laptop without Docker), the API falls back to in-process work.
"""
import json
import logging

from app.config import get_settings

log = logging.getLogger(__name__)


class AnalysisPublisher:
    def __init__(self):
        self._conn = None
        self._channel = None

    @property
    def enabled(self) -> bool:
        return self._channel is not None

    async def start(self) -> None:
        s = get_settings()
        if not s.rabbitmq_enabled:
            return
        import aio_pika

        try:
            self._conn = await aio_pika.connect_robust(s.rabbitmq_url)
            self._channel = await self._conn.channel()
            await self._channel.declare_queue(s.analysis_queue, durable=True)
        except Exception as exc:  # broker down: fall back instead of refusing to boot
            log.warning("RabbitMQ unavailable (%s); analysis will run in-process", exc)
            self._conn = self._channel = None

    async def publish(self, link_ids: list[int]) -> None:
        import aio_pika

        for link_id in link_ids:
            await self._channel.default_exchange.publish(
                aio_pika.Message(json.dumps({"link_id": link_id}).encode(),
                                 delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key=get_settings().analysis_queue)

    async def stop(self) -> None:
        if self._conn is not None:
            await self._conn.close()


class ClickPublisher:
    def __init__(self):
        self._producer = None

    @property
    def enabled(self) -> bool:
        return self._producer is not None

    async def start(self) -> None:
        s = get_settings()
        if not s.kafka_enabled:
            return
        from aiokafka import AIOKafkaProducer

        try:
            self._producer = AIOKafkaProducer(bootstrap_servers=s.kafka_bootstrap, linger_ms=20)
            await self._producer.start()
        except Exception as exc:
            log.warning("Kafka unavailable (%s); clicks will be written directly", exc)
            self._producer = None

    async def publish(self, event: dict) -> None:
        await self._producer.send(get_settings().clicks_topic, json.dumps(event).encode(),
                                  key=str(event["link_id"]).encode())

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()


analysis_publisher = AnalysisPublisher()
click_publisher = ClickPublisher()
