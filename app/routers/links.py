from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.config import get_settings
from app.db import get_session
from app.models import AnalysisStatus, ClickEvent, Link, RiskLevel, User
from app.schemas import BatchResult, DailyClicks, LinkBatchCreate, LinkCreate, LinkOut, LinkPage, LinkStats
from app.demo import get_writable_user
from app.security import get_current_user
from app.services import enqueue_analysis, to_out, unique_code

router = APIRouter(prefix="/api/links", tags=["links"])


async def _owned(session: AsyncSession, link_id: int, user: User) -> Link:
    link = await session.get(Link, link_id)
    if link is None or link.owner_id != user.id:
        raise HTTPException(404, "Link not found")
    return link


@router.post("", response_model=LinkOut, status_code=201)
async def create_link(body: LinkCreate, request: Request, background: BackgroundTasks,
                      user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    await cache.rate_limit(request, "create", str(user.id))
    if body.alias:
        if await session.scalar(select(Link.id).where(Link.short_code == body.alias)):
            raise HTTPException(409, "Alias already taken")
        code = body.alias
    else:
        code = await unique_code(session)
    link = Link(owner_id=user.id, short_code=code, original_url=str(body.url))
    session.add(link)
    await session.commit()
    await enqueue_analysis([link.id], background)
    return to_out(link)


@router.post("/batch", response_model=BatchResult, status_code=201)
async def create_batch(body: LinkBatchCreate, request: Request, background: BackgroundTasks,
                       user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    """Create many links in one transaction and queue one analysis job per link."""
    limit = get_settings().batch_max_urls
    if len(body.urls) > limit:
        raise HTTPException(422, f"At most {limit} URLs per batch")
    await cache.rate_limit(request, "create", str(user.id))
    taken: set[str] = set()
    links = []
    for url in body.urls:
        links.append(Link(owner_id=user.id, short_code=await unique_code(session, taken), original_url=str(url)))
    session.add_all(links)
    await session.commit()
    await enqueue_analysis([l.id for l in links], background)
    return BatchResult(created=[to_out(l) for l in links], queued_for_analysis=len(links))


@router.get("", response_model=LinkPage)
async def list_links(cursor: int | None = None, limit: int = Query(20, ge=1, le=100),
                     risk: RiskLevel | None = None, q: str | None = Query(None, max_length=200),
                     user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Keyset pagination (newest first): pass next_cursor back as `cursor`."""
    stmt = select(Link).where(Link.owner_id == user.id)
    if cursor:
        stmt = stmt.where(Link.id < cursor)
    if risk:
        stmt = stmt.where(Link.risk_level == risk)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Link.original_url).like(like) | func.lower(func.coalesce(Link.title, "")).like(like))
    rows = (await session.scalars(stmt.order_by(Link.id.desc()).limit(limit + 1))).all()
    items = rows[:limit]
    return LinkPage(items=[to_out(l) for l in items], next_cursor=items[-1].id if len(rows) > limit else None)


@router.get("/{link_id}", response_model=LinkOut)
async def get_link(link_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return to_out(await _owned(session, link_id, user))


@router.delete("/{link_id}", status_code=204)
async def delete_link(link_id: int, user: User = Depends(get_writable_user),
                      session: AsyncSession = Depends(get_session)):
    link = await _owned(session, link_id, user)
    code = link.short_code
    await session.delete(link)
    await session.commit()
    await cache.invalidate_link(code)


@router.post("/{link_id}/reanalyze", response_model=LinkOut)
async def reanalyze(link_id: int, background: BackgroundTasks, user: User = Depends(get_writable_user),
                    session: AsyncSession = Depends(get_session)):
    link = await _owned(session, link_id, user)
    link.status = AnalysisStatus.pending
    await session.commit()
    await enqueue_analysis([link.id], background)
    return to_out(link)


@router.get("/{link_id}/stats", response_model=LinkStats)
async def stats(link_id: int, days: int = Query(14, ge=1, le=90), user: User = Depends(get_current_user),
                session: AsyncSession = Depends(get_session)):
    link = await _owned(session, link_id, user)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    day = func.date(ClickEvent.clicked_at)
    rows = (await session.execute(
        select(day, func.count()).where(ClickEvent.link_id == link.id, ClickEvent.clicked_at >= since)
        .group_by(day).order_by(day))).all()
    refs = (await session.execute(
        select(ClickEvent.referrer, func.count().label("n")).where(ClickEvent.link_id == link.id)
        .group_by(ClickEvent.referrer).order_by(func.count().desc()).limit(5))).all()
    return LinkStats(link_id=link.id, total_clicks=link.click_count,
                     daily=[DailyClicks(day=str(d), clicks=n) for d, n in rows],
                     top_referrers=[{"referrer": r or "(direct)", "clicks": n} for r, n in refs])
