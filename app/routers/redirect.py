"""The hot path: resolve a short code and redirect. Redis cache-aside in front of PostgreSQL; clicks go to Kafka."""
import html

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.db import get_session
from app.models import Link
from app.services import record_click, utc_iso

router = APIRouter(tags=["redirect"])

WARNING = """<!doctype html><meta charset="utf-8"><title>LinkMind warning</title>
<body style="font-family:system-ui;max-width:560px;margin:80px auto;line-height:1.5">
<h2>{heading}</h2><p>LinkMind's analysis flagged this destination:</p><ul>{reasons}</ul>
<p><code>{url}</code></p>{action}</body>"""


async def resolve(code: str, session: AsyncSession) -> dict | None:
    data = await cache.get_cached_link(code)
    if data is not None:
        return data
    row = (await session.execute(
        select(Link.id, Link.original_url, Link.risk_level, Link.risk_reasons).where(Link.short_code == code))).first()
    if row is None:
        return None
    data = {"id": row.id, "url": row.original_url, "risk": row.risk_level.value, "reasons": row.risk_reasons or []}
    await cache.cache_link(code, data)
    return data


@router.get("/r/{code}", include_in_schema=True)
async def follow(code: str, request: Request, background: BackgroundTasks, confirm: bool = False,
                 session: AsyncSession = Depends(get_session)):
    data = await resolve(code, session)
    if data is None:
        raise HTTPException(404, "Short link not found")
    reasons = "".join(f"<li>{html.escape(r)}</li>" for r in data["reasons"][:6])
    url = html.escape(data["url"])
    if data["risk"] == "malicious":
        return HTMLResponse(WARNING.format(heading="Blocked: this link is reported as malicious", reasons=reasons,
                                           url=url, action=""), status_code=403)
    if data["risk"] == "suspicious" and not confirm:
        action = '<p><a href="?confirm=1">Continue anyway</a></p>'
        return HTMLResponse(WARNING.format(heading="This link looks suspicious", reasons=reasons, url=url,
                                           action=action), status_code=200)
    await record_click({"link_id": data["id"], "ts": utc_iso(),
                        "referrer": (request.headers.get("referer") or "")[:500] or None,
                        "user_agent": (request.headers.get("user-agent") or "")[:300] or None}, background)
    return RedirectResponse(data["url"], status_code=307)
