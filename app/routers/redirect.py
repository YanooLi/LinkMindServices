"""docs/SmartUrl-api.md §2.2 and §3.3: the redirect hot path. Redis cache-aside in front of PostgreSQL; unsafe
destinations get 403; every visit is published to Kafka (device type, country, referrer)."""
import html

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.db import get_session
from app.models import AiAnalysis, QrCode, Url
from app.services import RESERVED, record_event, visit_event

router = APIRouter(tags=["redirect"])
CODE = r"^[A-Za-z0-9_-]{3,40}$"

BLOCKED = """<!doctype html><meta charset="utf-8"><title>Link blocked · LinkMind</title>
<body style="font-family:system-ui;max-width:560px;margin:80px auto;padding:0 16px;line-height:1.5;color:#1a1c1f">
<h2 style="color:#ba1a1a">This link was blocked</h2>
<p>LinkMind's safety analysis flagged the destination as unsafe:</p><ul>{reasons}</ul>
<p style="word-break:break-all;color:#444653"><code>{url}</code></p></body>"""


async def resolve(session: AsyncSession, rtype: str, rid: str) -> dict | None:
    data = await cache.get_cached(rtype, rid)
    if data is not None:
        return data
    model, col = (Url, Url.short_code) if rtype == "url" else (QrCode, QrCode.qr_code_id)
    row = (await session.execute(select(model.original_url, model.is_safe).where(col == rid))).first()
    if row is None:
        return None
    reasons = []
    if not row.is_safe:
        reasons = await session.scalar(select(AiAnalysis.reasons).where(AiAnalysis.resource_type == rtype,
                                                                        AiAnalysis.resource_id == rid)) or []
    data = {"url": row.original_url, "is_safe": row.is_safe, "reasons": reasons}
    await cache.set_cached(rtype, rid, data)
    return data


async def follow(request: Request, background: BackgroundTasks, session: AsyncSession, rtype: str, rid: str):
    data = await resolve(session, rtype, rid)
    if data is None:
        raise HTTPException(404, "Short URL not found" if rtype == "url" else "QR code not found")
    if not data["is_safe"]:
        reasons = "".join(f"<li>{html.escape(r)}</li>" for r in data["reasons"][:6])
        return HTMLResponse(BLOCKED.format(reasons=reasons, url=html.escape(data["url"])), status_code=403)
    await record_event(visit_event(request, rtype, rid), background)
    return RedirectResponse(data["url"], status_code=307)


@router.get("/qrcode/{qr_code_id}", include_in_schema=True)
async def follow_qr(request: Request, background: BackgroundTasks, qr_code_id: str = Path(pattern=CODE),
                    session: AsyncSession = Depends(get_session)):
    return await follow(request, background, session, "qrcode", qr_code_id)


@router.get("/{short_code}")
async def follow_url(request: Request, background: BackgroundTasks, short_code: str = Path(pattern=CODE),
                     session: AsyncSession = Depends(get_session)):
    if short_code.lower() in RESERVED:
        raise HTTPException(404, "Not found")
    return await follow(request, background, session, "url", short_code)
