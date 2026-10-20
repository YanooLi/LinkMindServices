"""Shared operations used by several routers."""
import secrets
import string
from datetime import datetime, timezone

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.analysis.analyzer import analyze_link
from app.config import get_settings
from app.messaging import analysis_publisher, click_publisher
from app.models import ClickEvent, Link
from app.schemas import LinkOut

ALPHABET = string.ascii_letters + string.digits


def new_code(length: int = 7) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


async def unique_code(session: AsyncSession, taken: set[str] | None = None) -> str:
    taken = taken if taken is not None else set()
    for _ in range(10):
        code = new_code()
        if code in taken:
            continue
        exists = await session.scalar(select(Link.id).where(Link.short_code == code))
        if not exists:
            taken.add(code)
            return code
    raise RuntimeError("could not allocate a unique short code")


def to_out(link: Link) -> LinkOut:
    out = LinkOut.model_validate(link)
    out.short_url = f"{get_settings().public_base_url}/r/{link.short_code}"
    return out


async def _analyze_in_process(link_ids: list[int]) -> None:
    async with db.SessionLocal() as session:
        for link_id in link_ids:
            await analyze_link(session, link_id)


async def enqueue_analysis(link_ids: list[int], background: BackgroundTasks) -> None:
    """RabbitMQ when available; otherwise run after the response in this process."""
    if analysis_publisher.enabled:
        await analysis_publisher.publish(link_ids)
    else:
        background.add_task(_analyze_in_process, link_ids)


async def _write_click(event: dict) -> None:
    async with db.SessionLocal() as session:
        await persist_clicks(session, [event])


async def persist_clicks(session: AsyncSession, events: list[dict]) -> None:
    """Insert click events and bump each link's counter (used by the Kafka consumer and the fallback)."""
    counts: dict[int, int] = {}
    for e in events:
        session.add(ClickEvent(link_id=e["link_id"], referrer=e.get("referrer"), user_agent=e.get("user_agent"),
                               clicked_at=datetime.fromisoformat(e["ts"])))
        counts[e["link_id"]] = counts.get(e["link_id"], 0) + 1
    for link_id, n in counts.items():
        link = await session.get(Link, link_id)
        if link is not None:
            link.click_count += n
    await session.commit()


async def record_click(event: dict, background: BackgroundTasks) -> None:
    if click_publisher.enabled:
        await click_publisher.publish(event)
    else:
        background.add_task(_write_click, event)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
