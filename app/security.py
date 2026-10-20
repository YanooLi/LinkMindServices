"""Password hashing (bcrypt) and JWT access/refresh tokens (docs/SmartUrl-api.md §1)."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str | None) -> bool:
    return bool(hashed) and bcrypt.checkpw(password.encode(), hashed.encode())


def _token(user_id: int, kind: str, seconds: int) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "type": kind, "iat": now, "exp": now + timedelta(seconds=seconds)}
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_access_token(user_id: int) -> str:
    return _token(user_id, "access", get_settings().jwt_access_expire)


def create_refresh_token(user_id: int) -> str:
    return _token(user_id, "refresh", get_settings().jwt_refresh_expire)


def decode_token(token: str, kind: str) -> int:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
        if payload.get("type") != kind:
            raise ValueError("wrong token type")
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer),
                           session: AsyncSession = Depends(get_session)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    user = await session.get(User, decode_token(creds.credentials, "access"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User no longer exists", headers={"WWW-Authenticate": "Bearer"})
    return user
