"""Public read-only demo account, seeded on startup when DEMO_EMAIL/DEMO_PASSWORD are set.

Lets a visitor (e.g. an interviewer) try LinkMind without registering, while the account cannot create, delete
or re-analyze links, so the public deployment cannot be used to mint redirect links.
"""
from fastapi import BackgroundTasks, Depends, HTTPException
from sqlalchemy import select

from app import db
from app.config import get_settings
from app.models import Link, User
from app.security import get_current_user, hash_password, verify_password

SAMPLE_URLS = [
    "https://github.com/YanooLi/LinkMindServices",
    "https://www.cmu.edu/",
    "https://news.ycombinator.com/",
    "https://www.youtube.com/",
    "http://paypal-account-verify.top/login",   # deliberately phishing-shaped: shows the risk analysis
]


def is_demo(user: User) -> bool:
    email = get_settings().demo_email
    return bool(email) and user.email == email.lower()


async def get_writable_user(user: User = Depends(get_current_user)) -> User:
    if is_demo(user):
        raise HTTPException(403, "The demo account is read-only. Create your own account to add links.")
    return user


async def seed_demo() -> list[int]:
    """Create the demo user and its sample links if missing; returns ids of links that need analysis."""
    s = get_settings()
    if not (s.demo_email and s.demo_password):
        return []
    from app.services import unique_code

    async with db.SessionLocal() as session:
        email = s.demo_email.lower()
        user = await session.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, hashed_password=hash_password(s.demo_password))
            session.add(user)
            await session.flush()
        elif not verify_password(s.demo_password, user.hashed_password):
            user.hashed_password = hash_password(s.demo_password)
        if await session.scalar(select(Link.id).where(Link.owner_id == user.id).limit(1)):
            await session.commit()
            return []
        links = [Link(owner_id=user.id, short_code=await unique_code(session), original_url=u) for u in SAMPLE_URLS]
        session.add_all(links)
        await session.commit()
        return [l.id for l in links]


async def seed_and_analyze() -> None:
    from app.services import enqueue_analysis

    ids = await seed_demo()
    if ids:
        tasks = BackgroundTasks()
        await enqueue_analysis(ids, tasks)
        await tasks()
