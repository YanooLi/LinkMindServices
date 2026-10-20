import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import rate_limit
from app.db import get_session
from app.models import User
from app.config import get_settings
from app.schemas import PublicConfig, Token, UserCreate, UserOut
from app.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: UserCreate, request: Request, session: AsyncSession = Depends(get_session)):
    await rate_limit(request, "register", request.client.host if request.client else "?")
    code = get_settings().registration_invite_code
    if code and not (body.invite_code and secrets.compare_digest(body.invite_code, code)):
        raise HTTPException(403, "A valid invite code is required to register")
    email = body.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, hashed_password=hash_password(body.password))
    session.add(user)
    await session.commit()
    return user


@router.post("/token", response_model=Token)
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends(),
                session: AsyncSession = Depends(get_session)):
    """OAuth2 password flow: form fields `username` (the email) and `password`."""
    await rate_limit(request, "login", request.client.host if request.client else "?")
    user = await session.scalar(select(User).where(User.email == form.username.lower()))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})
    return Token(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user


@router.get("/config", response_model=PublicConfig)
async def public_config():
    """What the login page needs to know: whether sign-up needs an invite, and the public demo login."""
    s = get_settings()
    demo = bool(s.demo_email and s.demo_password)
    return PublicConfig(registration_requires_invite=bool(s.registration_invite_code),
                        demo_email=s.demo_email if demo else None, demo_password=s.demo_password if demo else None)
