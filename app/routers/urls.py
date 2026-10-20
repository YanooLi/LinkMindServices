"""docs/SmartUrl-api.md §2.1 and §5.1: create short URLs and list the user's history. Plus batch create and delete."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.config import get_settings
from app.db import get_session
from app.demo import get_writable_user
from app.models import AiAnalysis, Url, User
from app.schemas import ShortenBatchIn, ShortenIn, UrlHistory, UrlOut
from app.security import get_current_user
from app.services import RESERVED, analyses_for, enqueue_analysis, unique_code, url_out

router = APIRouter(tags=["short urls"])


@router.post("/shorten/", response_model=UrlOut, status_code=201)
async def shorten(body: ShortenIn, request: Request, background: BackgroundTasks,
                  user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    """Analysis runs asynchronously: `ai_analysis` is null until the worker finishes (poll /ai/analysis/url/{code})."""
    await cache.rate_limit(request, "create", str(user.id))
    if body.custom_alias:
        alias = body.custom_alias
        if alias.lower() in RESERVED:
            raise HTTPException(409, f"'{alias}' is reserved. Choose another custom back-half")
        # Case-insensitive so "I20" and "i20" can't point to different places.
        if await session.scalar(select(Url.id).where(func.lower(Url.short_code) == alias.lower())):
            raise HTTPException(409, f"'{alias}' is already taken. Choose another custom back-half")
        code = alias
    else:
        code = await unique_code(session, Url, Url.short_code)
    url = Url(user_id=user.id, original_url=str(body.target_url), title=body.title or None, ai_enabled=body.ai_enabled,
              short_code=code)
    session.add(url)
    try:
        await session.commit()
    except IntegrityError:          # lost a race for the same alias
        await session.rollback()
        raise HTTPException(409, f"'{code}' is already taken. Choose another custom back-half")
    await enqueue_analysis([("url", url.short_code)], background)
    return url_out(url, None)


@router.post("/shorten/batch", response_model=list[UrlOut], status_code=201)
async def shorten_batch(body: ShortenBatchIn, request: Request, background: BackgroundTasks,
                        user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    """Create up to batch_max_urls short URLs in one transaction; one analysis job per URL goes to RabbitMQ."""
    if len(body.target_urls) > get_settings().batch_max_urls:
        raise HTTPException(422, f"At most {get_settings().batch_max_urls} URLs per batch")
    await cache.rate_limit(request, "create", str(user.id))
    taken: set[str] = set()
    urls = [Url(user_id=user.id, original_url=str(u), ai_enabled=body.ai_enabled,
                short_code=await unique_code(session, Url, Url.short_code, taken=taken)) for u in body.target_urls]
    session.add_all(urls)
    await session.commit()
    await enqueue_analysis([("url", u.short_code) for u in urls], background)
    return [url_out(u, None) for u in urls]


@router.get("/urls/history", response_model=UrlHistory)
async def url_history(page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=100),
                      sort: str = Query("created_at", pattern="^(created_at|clicks)$"),
                      order: str = Query("desc", pattern="^(asc|desc)$"), q: str | None = Query(None, max_length=200),
                      user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    base = select(Url).where(Url.user_id == user.id)
    if q:
        like = f"%{q.lower()}%"
        base = base.where(func.lower(Url.original_url).like(like) | func.lower(func.coalesce(Url.title, "")).like(like))
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    col = Url.clicks if sort == "clicks" else Url.created_at
    rows = (await session.scalars(base.order_by(col.desc() if order == "desc" else col.asc(), Url.id.desc())
                                  .offset((page - 1) * limit).limit(limit))).all()
    an = await analyses_for(session, "url", [u.short_code for u in rows])
    return UrlHistory(page=page, limit=limit, total=total, urls=[url_out(u, an.get(u.short_code)) for u in rows])


@router.get("/urls/{short_code}", response_model=UrlOut)
async def get_url(short_code: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    url = await session.scalar(select(Url).where(Url.short_code == short_code, Url.user_id == user.id))
    if url is None:
        raise HTTPException(404, "Short URL not found")
    return url_out(url, (await analyses_for(session, "url", [short_code])).get(short_code))


@router.delete("/urls/{short_code}", status_code=204)
async def delete_url(short_code: str, user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    url = await session.scalar(select(Url).where(Url.short_code == short_code, Url.user_id == user.id))
    if url is None:
        raise HTTPException(404, "Short URL not found")
    await session.delete(url)
    await session.execute(delete(AiAnalysis).where(AiAnalysis.resource_type == "url", AiAnalysis.resource_id == short_code))
    await session.commit()
    await cache.invalidate("url", short_code)
