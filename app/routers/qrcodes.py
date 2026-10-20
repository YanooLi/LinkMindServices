"""docs/SmartUrl-api.md §3 and §5.2: QR codes (generated on demand, never stored as images) and their history."""
import io

import qrcode
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers.pil import CircleModuleDrawer, RoundedModuleDrawer, SquareModuleDrawer
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.config import get_settings
from app.db import get_session
from app.demo import get_writable_user
from app.models import AiAnalysis, QrCode, User
from app.schemas import QrHistory, QrIn, QrOut
from app.security import get_current_user
from app.services import analyses_for, enqueue_analysis, qr_out, unique_code

router = APIRouter(tags=["qr codes"])
DRAWERS = {"square": SquareModuleDrawer, "rounded": RoundedModuleDrawer, "dots": CircleModuleDrawer}


@router.post("/qrcode/", response_model=QrOut, status_code=201)
async def create_qr(body: QrIn, request: Request, background: BackgroundTasks,
                    user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    await cache.rate_limit(request, "create", str(user.id))
    qr = QrCode(user_id=user.id, original_url=str(body.target_url), title=body.title or None, ai_enabled=body.ai_enabled,
                color=body.color, style=body.style,
                qr_code_id=await unique_code(session, QrCode, QrCode.qr_code_id, prefix="qr", length=6))
    session.add(qr)
    await session.commit()
    await enqueue_analysis([("qrcode", qr.qr_code_id)], background)
    return qr_out(qr, None)


def render_png(data: str, color: str, style: str, size: int = 10) -> bytes:
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=size, border=2)
    q.add_data(data)
    q.make(fit=True)
    rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
    img = q.make_image(image_factory=StyledPilImage, module_drawer=DRAWERS.get(style, SquareModuleDrawer)(),
                       color_mask=SolidFillColorMask(front_color=rgb, back_color=(255, 255, 255)))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/qrcode/preview", responses={200: {"content": {"image/png": {}}}})
async def qr_preview(request: Request, target_url: str = Query(min_length=1, max_length=2048),
                     color: str = Query("#000000", pattern=r"^#[0-9A-Fa-f]{6}$"),
                     style: str = Query("square", pattern=r"^(square|rounded|dots)$"),
                     user: User = Depends(get_current_user)):
    """Live preview for the QR Generator: renders the destination itself in the chosen color and style. Nothing is
    stored; the real code (created by POST /qrcode/) encodes the tracked /qrcode/{id} URL instead."""
    await cache.rate_limit(request, "qr-preview", str(user.id))
    return Response(render_png(target_url, color, style, 8), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/qrcode/{qr_code_id}/image", responses={200: {"content": {"image/png": {}}}})
async def qr_image(qr_code_id: str, size: int = Query(10, ge=4, le=20), session: AsyncSession = Depends(get_session)):
    """PNG generated on demand; it encodes the tracked /qrcode/{id} URL so every scan is counted."""
    qr = await session.scalar(select(QrCode).where(QrCode.qr_code_id == qr_code_id))
    if qr is None:
        raise HTTPException(404, "QR code not found")
    png = render_png(f"{get_settings().public_base_url}/qrcode/{qr_code_id}", qr.color, qr.style, size)
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/qrcodes/history", response_model=QrHistory)
async def qr_history(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                     sort: str = Query("created_at", pattern="^(created_at|scans)$"),
                     order: str = Query("desc", pattern="^(asc|desc)$"), q: str | None = Query(None, max_length=200),
                     user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    base = select(QrCode).where(QrCode.user_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        base = base.where(func.lower(QrCode.original_url).like(like) | func.lower(func.coalesce(QrCode.title, "")).like(like))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    col = QrCode.scans if sort == "scans" else QrCode.created_at
    rows = (await session.scalars(base.order_by(col.desc() if order == "desc" else col.asc(), QrCode.id.desc())
                                  .offset((page - 1) * limit).limit(limit))).all()
    an = await analyses_for(session, "qrcode", [r.qr_code_id for r in rows])
    return QrHistory(page=page, limit=limit, total=total, qrcodes=[qr_out(r, an.get(r.qr_code_id)) for r in rows])


@router.delete("/qrcode/{qr_code_id}", status_code=204)
async def delete_qr(qr_code_id: str, user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    qr = await session.scalar(select(QrCode).where(QrCode.qr_code_id == qr_code_id, QrCode.user_id == user.id))
    if qr is None:
        raise HTTPException(404, "QR code not found")
    await session.delete(qr)
    await session.execute(delete(AiAnalysis).where(AiAnalysis.resource_type == "qrcode", AiAnalysis.resource_id == qr_code_id))
    await session.commit()
    await cache.invalidate("qrcode", qr_code_id)
