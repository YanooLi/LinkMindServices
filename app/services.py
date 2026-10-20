"""Shared operations: code generation, response shaping, analysis queueing and visit-event recording."""
import re
import secrets
import string
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import BackgroundTasks, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.analysis.analyzer import analyze_resource
from app.config import get_settings
from app.messaging import analysis_publisher, click_publisher
from app.models import AiAnalysis, AnalyticsEvent, QrCode, Url
from app.schemas import AnalysisBrief, QrOut, UrlOut

ALPHABET = string.ascii_letters + string.digits
RESERVED = {"docs", "redoc", "openapi.json", "health", "auth", "users", "shorten", "qrcode", "qrcodes", "urls", "ai",
            "analytics", "favicon.ico", "robots.txt"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def unique_code(session: AsyncSession, model, column, prefix: str = "", length: int = 7,
                      taken: set[str] | None = None) -> str:
    taken = taken if taken is not None else set()
    for _ in range(10):
        code = prefix + "".join(secrets.choice(ALPHABET) for _ in range(length))
        if code in taken or code.lower() in RESERVED:
            continue
        if not await session.scalar(select(model.id).where(column == code)):
            taken.add(code)
            return code
    raise RuntimeError("could not allocate a unique code")


async def analyses_for(session: AsyncSession, resource_type: str, ids: list[str]) -> dict[str, AiAnalysis]:
    if not ids:
        return {}
    rows = await session.scalars(select(AiAnalysis).where(AiAnalysis.resource_type == resource_type,
                                                          AiAnalysis.resource_id.in_(ids)))
    return {r.resource_id: r for r in rows}


def brief(a: AiAnalysis | None) -> AnalysisBrief | None:
    if a is None or a.status != "done":
        return None
    return AnalysisBrief(category=a.category, is_safe=a.is_safe, safety_score=a.safety_score, checked_at=a.analyzed_at)


def url_out(u: Url, a: AiAnalysis | None) -> UrlOut:
    base = get_settings().public_base_url
    return UrlOut(original_url=u.original_url, short_code=u.short_code, short_url=f"{base}/{u.short_code}", title=u.title,
                  clicks=u.clicks, is_safe=u.is_safe, user_id=u.user_id, ai_enabled=u.ai_enabled, ai_analysis=brief(a),
                  category=a.category if a else None, created_at=u.created_at)


def qr_out(q: QrCode, a: AiAnalysis | None) -> QrOut:
    base = get_settings().public_base_url
    return QrOut(original_url=q.original_url, qr_code_id=q.qr_code_id, qr_code_url=f"{base}/qrcode/{q.qr_code_id}",
                 image_url=f"{base}/qrcode/{q.qr_code_id}/image", title=q.title, scans=q.scans, is_safe=q.is_safe,
                 user_id=q.user_id, ai_enabled=q.ai_enabled, color=q.color, style=q.style, ai_analysis=brief(a),
                 category=a.category if a else None, created_at=q.created_at)


async def _analyze_in_process(items: list[tuple[str, str]]) -> None:
    async with db.SessionLocal() as session:
        for resource_type, resource_id in items:
            await analyze_resource(session, resource_type, resource_id)


async def enqueue_analysis(items: list[tuple[str, str]], background: BackgroundTasks) -> None:
    """RabbitMQ when available; otherwise run after the response in this process."""
    if analysis_publisher.enabled:
        await analysis_publisher.publish(items)
    else:
        background.add_task(_analyze_in_process, items)


# ---------------- visit events (clicks and scans) ----------------
def device_type(user_agent: str | None) -> str:
    ua = (user_agent or "").lower()
    if re.search(r"ipad|tablet|kindle|silk|(android(?!.*mobile))", ua):
        return "tablet"
    if re.search(r"mobi|iphone|ipod|android|blackberry|opera mini|windows phone", ua):
        return "mobile"
    return "desktop"


_geo = None


def country_of(ip: str | None) -> str | None:
    """Offline IP → country (geoip2fast's bundled database). The IP itself is never stored."""
    global _geo
    if not ip:
        return None
    try:
        if _geo is None:
            from geoip2fast import GeoIP2Fast
            _geo = GeoIP2Fast()
        r = _geo.lookup(ip)
        return r.country_name if r.country_code and r.country_code not in ("--", "") else None
    except Exception:
        return None


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd and get_settings().trust_forwarded_for:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def referrer_host(referer: str | None) -> str | None:
    host = urlsplit(referer).hostname if referer else None
    return host.removeprefix("www.") if host else None


def visit_event(request: Request, resource_type: str, resource_id: str) -> dict:
    """Raw facts only, so the redirect stays cheap; the Kafka consumer derives device type, country and referrer host.
    The IP travels in the event and is used once for the country lookup; it is never written to the database."""
    return {"resource_type": resource_type, "resource_id": resource_id,
            "event_type": "click" if resource_type == "url" else "scan", "ts": utcnow().isoformat(),
            "ip": client_ip(request), "ua": (request.headers.get("user-agent") or "")[:400],
            "referer": (request.headers.get("referer") or "")[:500]}


def enrich(e: dict) -> dict:
    return {"device_type": e.get("device_type") or device_type(e.get("ua")),
            "country": e.get("country") or country_of(e.get("ip")),
            "referrer": e.get("referrer") or referrer_host(e.get("referer"))}


async def persist_events(session: AsyncSession, events: list[dict]) -> None:
    """Insert analytics rows and bump clicks/scans (used by the Kafka consumer and the in-process fallback)."""
    counts: dict[tuple[str, str], int] = {}
    for e in events:
        session.add(AnalyticsEvent(resource_type=e["resource_type"], resource_id=e["resource_id"], event_type=e["event_type"],
                                   event_date=datetime.fromisoformat(e["ts"]), **enrich(e)))
        key = (e["resource_type"], e["resource_id"])
        counts[key] = counts.get(key, 0) + 1
    for (rtype, rid), n in counts.items():
        if rtype == "url":
            row = await session.scalar(select(Url).where(Url.short_code == rid))
            if row is not None:
                row.clicks += n
        else:
            row = await session.scalar(select(QrCode).where(QrCode.qr_code_id == rid))
            if row is not None:
                row.scans += n
    await session.commit()


async def _write_event(event: dict) -> None:
    async with db.SessionLocal() as session:
        await persist_events(session, [event])


async def record_event(event: dict, background: BackgroundTasks) -> None:
    if click_publisher.enabled:
        await click_publisher.publish(event)
    else:
        background.add_task(_write_event, event)
