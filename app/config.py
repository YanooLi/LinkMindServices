"""Settings, read from environment variables / .env (see .env.example)."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LinkMind"
    database_url: str = "postgresql+asyncpg://linkmind:linkmind@localhost:5433/linkmind"
    redis_url: str = "redis://localhost:6380/0"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    kafka_bootstrap: str = "localhost:9092"

    # Feature switches. With a switch off the API falls back to in-process work, so it runs (and is
    # testable) without that piece of infrastructure, and the load test can compare cache on vs off.
    cache_enabled: bool = True
    rabbitmq_enabled: bool = True
    kafka_enabled: bool = True

    jwt_secret: str = ""
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24

    public_base_url: str = "http://localhost:8000"
    cors_origins: str = "http://localhost:5173"
    cache_ttl_seconds: int = 3600
    rate_limit_per_minute: int = 60
    batch_max_urls: int = 100

    # Optional AI / security providers. Every one degrades gracefully when its key is empty.
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    huggingface_token: str = ""
    huggingface_model: str = "facebook/bart-large-mnli"
    safe_browsing_api_key: str = ""
    fetch_page_metadata: bool = True

    # Hosted deployment (docs/DEPLOY.md)
    embedded_workers: bool = False         # run the RabbitMQ + Kafka consumers inside the API process
    registration_invite_code: str = ""     # when set, /register requires it (keeps a public shortener from abuse)
    demo_email: str = ""                   # when set, a read-only demo account with sample links is seeded
    demo_password: str = ""
    kafka_security_protocol: str = "PLAINTEXT"   # SASL_SSL for hosted Kafka (e.g. Aiven)
    kafka_sasl_mechanism: str = "SCRAM-SHA-256"
    kafka_username: str = ""
    kafka_password: str = ""
    kafka_ca_cert: str = ""                # PEM text of the provider's CA certificate
    kafka_access_cert: str = ""            # PEM client certificate (Aiven "Client certificate" auth, protocol SSL)
    kafka_access_key: str = ""             # PEM client key

    analysis_queue: str = "link.analyze"
    clicks_topic: str = "link.clicks"

    @field_validator("jwt_secret")
    @classmethod
    def _strong_secret(cls, v: str) -> str:
        # Several API processes must share one secret, so it is never generated at startup.
        if len(v) < 32:
            raise ValueError('JWT_SECRET must be set to 32+ characters in .env; generate one with: '
                             'python3 -c "import secrets;print(secrets.token_hex(32))"')
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
