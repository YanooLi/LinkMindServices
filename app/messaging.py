"""Message brokers.

* RabbitMQ (aio-pika): work queue of link-analysis jobs, consumed by worker/analysis_worker.py. Batch creation
  publishes one message per link so analysis scales with the number of worker processes, not API requests.
* Kafka (aiokafka): append-only stream of click events, consumed by worker/click_consumer.py, which writes them
  in batches. The redirect path only appends to the log, so a burst of clicks never waits on the database.

When a broker is disabled (tests, a laptop without Docker), the API falls back to in-process work.
"""
import json
import logging
import os
import tempfile

from app.config import get_settings

log = logging.getLogger(__name__)


def _pem_file(pem: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(fd, "w") as f:
        f.write(pem.replace("\\n", "\n"))
    return path


def kafka_kwargs() -> dict:
    """Connection settings shared by the producer and the consumer; SASL_SSL for hosted Kafka (Aiven)."""
    s = get_settings()
    kw = {"bootstrap_servers": s.kafka_bootstrap, "security_protocol": s.kafka_security_protocol}
    if s.kafka_security_protocol in ("SSL", "SASL_SSL"):
        from aiokafka.helpers import create_ssl_context

        certfile = keyfile = None
        if s.kafka_access_cert and s.kafka_access_key:
            # ssl needs files for the client certificate; write the PEM env vars to private temp files.
            certfile, keyfile = _pem_file(s.kafka_access_cert), _pem_file(s.kafka_access_key)
        kw["ssl_context"] = create_ssl_context(cadata=s.kafka_ca_cert or None, certfile=certfile, keyfile=keyfile)
    if s.kafka_security_protocol.startswith("SASL"):
        kw.update(sasl_mechanism=s.kafka_sasl_mechanism, sasl_plain_username=s.kafka_username,
                  sasl_plain_password=s.kafka_password)
    return kw


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

    async def publish(self, items: list[tuple[str, str]]) -> None:
        """One message per resource: {"resource_type": "url"|"qrcode", "resource_id": code}."""
        import aio_pika

        for resource_type, resource_id in items:
            await self._channel.default_exchange.publish(
                aio_pika.Message(json.dumps({"resource_type": resource_type, "resource_id": resource_id}).encode(),
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
            self._producer = AIOKafkaProducer(linger_ms=20, **kafka_kwargs())
            await self._producer.start()
        except Exception as exc:
            log.warning("Kafka unavailable (%s); clicks will be written directly", exc)
            self._producer = None

    async def publish(self, event: dict) -> None:
        await self._producer.send(get_settings().clicks_topic, json.dumps(event).encode(),
                                  key=f'{event["resource_type"]}:{event["resource_id"]}'.encode())

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()


analysis_publisher = AnalysisPublisher()
click_publisher = ClickPublisher()
