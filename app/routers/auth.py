"""docs/SmartUrl-api.md §1: register, login (JWT access + refresh), refresh. Logout is client-side."""
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import rate_limit
from app.config import get_settings
from app.db import get_session
from app.models import User
from app.schemas import AccessOut, LoginIn, LoginOut, PublicConfig, RefreshIn, RegisterIn, UserBrief, UserOut
from app.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _ip(request: Request) -> str:
    return request.client.host if request.client else "?"


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterIn, request: Request, session: AsyncSession = Depends(get_session)):
    await rate_limit(request, "register", _ip(request))
    code = get_settings().registration_invite_code
    if code and not (body.invite_code and secrets.compare_digest(body.invite_code, code)):
        raise HTTPException(403, "A valid invite code is required to register")
    email, username = body.email.lower(), body.username
    clash = await session.scalar(select(User).where(or_(User.email == email, User.username == username)))
    if clash:
        raise HTTPException(409, "Username already taken" if clash.username == username else "Email already registered")
    user = User(username=username, email=email, password_hash=hash_password(body.password))
    session.add(user)
    await session.commit()
    return user


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, request: Request, session: AsyncSession = Depends(get_session)):
    """Log in with username (or email) and password."""
    await rate_limit(request, "login", _ip(request))
    ident = body.username.strip()
    user = await session.scalar(select(User).where(or_(User.username == ident, User.email == ident.lower())))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Incorrect username or password")
    return LoginOut(access_token=create_access_token(user.id), refresh_token=create_refresh_token(user.id),
                    expires_in=get_settings().jwt_access_expire, user=UserBrief.model_validate(user))


@router.post("/refresh", response_model=AccessOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    user_id = decode_token(body.refresh_token, "refresh")
    if await session.get(User, user_id) is None:
        raise HTTPException(401, "User no longer exists")
    return AccessOut(access_token=create_access_token(user_id), expires_in=get_settings().jwt_access_expire)


@router.get("/config", response_model=PublicConfig)
async def public_config():
    """What the sign-in page needs: whether sign-up needs an invite, and the public read-only demo login."""
    s = get_settings()
    demo = bool(s.demo_username and s.demo_password)
    return PublicConfig(registration_requires_invite=bool(s.registration_invite_code),
                        demo_username=s.demo_username if demo else None, demo_password=s.demo_password if demo else None)
