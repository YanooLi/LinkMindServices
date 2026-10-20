"""docs/SmartUrl-api.md §1.6–1.7: profile; plus account deletion for Settings › Danger Zone."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.demo import get_writable_user
from app.models import QrCode, Url, User
from app.schemas import ProfileOut, ProfilePatch, UserOut, UserStats
from app.security import get_current_user

router = APIRouter(prefix="/users", tags=["users"])


async def _profile(session: AsyncSession, user: User) -> ProfileOut:
    urls = await session.scalar(select(func.count()).select_from(Url).where(Url.user_id == user.id))
    qrs = await session.scalar(select(func.count()).select_from(QrCode).where(QrCode.user_id == user.id))
    return ProfileOut(**UserOut.model_validate(user).model_dump(), stats=UserStats(urls_created=urls, qr_codes_created=qrs))


@router.get("/me", response_model=ProfileOut)
async def me(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _profile(session, user)


@router.patch("/me", response_model=ProfileOut)
async def update_me(body: ProfilePatch, user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    changes = body.model_dump(exclude_unset=True)
    if "email" in changes:
        changes["email"] = changes["email"].lower()
    clash_filters = []
    if changes.get("username") and changes["username"] != user.username:
        clash_filters.append(User.username == changes["username"])
    if changes.get("email") and changes["email"] != user.email:
        clash_filters.append(User.email == changes["email"])
    if clash_filters and await session.scalar(select(User.id).where(or_(*clash_filters))):
        raise HTTPException(409, "Username or email already in use")
    for k, v in changes.items():
        setattr(user, k, v)
    await session.commit()
    return await _profile(session, user)


@router.delete("/me", status_code=204)
async def delete_me(user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    """Deletes the account. Its links and QR codes keep working (user_id becomes NULL), per the schema design."""
    await session.delete(user)
    await session.commit()


@router.delete("/me/resources", status_code=204)
async def delete_all_resources(user: User = Depends(get_writable_user), session: AsyncSession = Depends(get_session)):
    """Settings › Danger Zone › Delete all links: removes every short URL and QR code this user created."""
    from sqlalchemy import delete as sql_delete

    from app import cache
    from app.models import AiAnalysis

    codes = (await session.scalars(select(Url.short_code).where(Url.user_id == user.id))).all()
    qids = (await session.scalars(select(QrCode.qr_code_id).where(QrCode.user_id == user.id))).all()
    await session.execute(sql_delete(AiAnalysis).where(
        ((AiAnalysis.resource_type == "url") & AiAnalysis.resource_id.in_(codes)) |
        ((AiAnalysis.resource_type == "qrcode") & AiAnalysis.resource_id.in_(qids))))
    await session.execute(sql_delete(Url).where(Url.user_id == user.id))
    await session.execute(sql_delete(QrCode).where(QrCode.user_id == user.id))
    await session.commit()
    for c in codes:
        await cache.invalidate("url", c)
    for q in qids:
        await cache.invalidate("qrcode", q)
