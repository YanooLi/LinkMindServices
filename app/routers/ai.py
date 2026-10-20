"""docs/SmartUrl-api.md §4: read a resource's analysis, or queue a re-analysis (202)."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.analyzer import get_or_create_analysis, load_resource
from app.db import get_session
from app.demo import get_writable_user
from app.models import User
from app.schemas import AnalysisDetail, AnalysisOut, GsbOut, ReanalyzeOut
from app.security import get_current_user
from app.services import analyses_for, enqueue_analysis, utcnow

router = APIRouter(prefix="/ai", tags=["ai analysis"])


async def _owned(session: AsyncSession, rtype: str, rid: str, user: User):
    res = await load_resource(session, rtype, rid)
    if res is None or res.user_id != user.id:
        raise HTTPException(404, "Resource not found")
    return res


async def _analysis(session: AsyncSession, rtype: str, rid: str, user: User) -> AnalysisOut:
    res = await _owned(session, rtype, rid, user)
    a = (await analyses_for(session, rtype, [rid])).get(rid)
    detail = None if a is None else AnalysisDetail(
        status=a.status, category=a.category, is_safe=a.is_safe, safety_score=a.safety_score, threat_types=a.threat_types or [],
        reasons=a.reasons or [], ai_provider=a.ai_provider, checked_at=a.analyzed_at,
        google_safe_browsing=GsbOut(is_safe=a.google_safe_browsing_safe, threat_types=a.google_safe_browsing_threats or []))
    key = {"short_code": rid} if rtype == "url" else {"qr_code_id": rid}
    return AnalysisOut(**key, original_url=res.original_url, analysis=detail)


@router.get("/analysis/url/{short_code}", response_model=AnalysisOut)
async def url_analysis(short_code: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _analysis(session, "url", short_code, user)


@router.get("/analysis/qrcode/{qr_code_id}", response_model=AnalysisOut)
async def qr_analysis(qr_code_id: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _analysis(session, "qrcode", qr_code_id, user)


@router.post("/reanalyze/{resource_type}/{resource_id}", response_model=ReanalyzeOut, status_code=202)
async def reanalyze(background: BackgroundTasks, resource_type: str = Path(pattern="^(url|qrcode)$"), resource_id: str = Path(),
                    user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    await _owned(session, resource_type, resource_id, user)
    row = await get_or_create_analysis(session, resource_type, resource_id)
    row.status = "pending"
    await session.commit()
    await enqueue_analysis([(resource_type, resource_id)], background)
    return ReanalyzeOut(message="Re-analysis queued", resource_type=resource_type, resource_id=resource_id, queued_at=utcnow())
