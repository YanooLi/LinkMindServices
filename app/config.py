"""Settings, read from environment variables / .env (see .env.example)."""
from functools import lru_cache

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

    jwt_secret: str = "change-me-in-production"
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

    analysis_queue: str = "link.analyze"
    clicks_topic: str = "link.clicks"


@lru_cache
def get_settings() -> Settings:
    return Settings()
