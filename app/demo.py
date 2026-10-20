"""Public read-only demo account, seeded on startup when DEMO_USERNAME/DEMO_PASSWORD are set.

A visitor (e.g. an interviewer) can try LinkMind without registering; the account cannot create, change or delete
anything, so the public deployment cannot be used to mint redirect links."""
from fastapi import BackgroundTasks, Depends, HTTPException
from sqlalchemy import select

from app import db
from app.config import get_settings
from app.models import QrCode, Url, User
from app.security import get_current_user, hash_password, verify_password

SAMPLE_URLS = [
    ("https://github.com/YanooLi/LinkMindServices", "LinkMind backend on GitHub"),
    ("https://www.cmu.edu/", None),
    ("https://news.ycombinator.com/", None),
    ("http://paypal-account-verify.top/login", None),   # deliberately phishing-shaped: shows the safety analysis
]
SAMPLE_QR = ("https://github.com/YanooLi/LinkMind-UI", "LinkMind UI repository", "#2E4BC8", "rounded")


def is_demo(user: User) -> bool:
    name = get_settings().demo_username
    return bool(name) and user.username == name


async def get_writable_user(user: User = Depends(get_current_user)) -> User:
    if is_demo(user):
        raise HTTPException(403, "The demo account is read-only. Create your own account to make changes.")
    return user


async def seed_demo() -> list[tuple[str, str]]:
    """Create the demo user and its samples if missing; returns resources that need analysis."""
    s = get_settings()
    if not (s.demo_username and s.demo_password):
        return []
    from app.services import unique_code

    async with db.SessionLocal() as session:
        user = await session.scalar(select(User).where(User.username == s.demo_username))
        if user is None:
            user = User(username=s.demo_username, email=f"{s.demo_username}@demo.linkmind.local",
                        password_hash=hash_password(s.demo_password), first_name="Demo", last_name="User")
            session.add(user)
            await session.flush()
        elif not verify_password(s.demo_password, user.password_hash):
            user.password_hash = hash_password(s.demo_password)
        if await session.scalar(select(Url.id).where(Url.user_id == user.id).limit(1)):
            await session.commit()
            return []
        urls = [Url(user_id=user.id, original_url=u, title=t, short_code=await unique_code(session, Url, Url.short_code))
                for u, t in SAMPLE_URLS]
        qr = QrCode(user_id=user.id, original_url=SAMPLE_QR[0], title=SAMPLE_QR[1], color=SAMPLE_QR[2], style=SAMPLE_QR[3],
                    qr_code_id=await unique_code(session, QrCode, QrCode.qr_code_id, prefix="qr", length=6))
        session.add_all(urls + [qr])
        await session.commit()
        return [("url", u.short_code) for u in urls] + [("qrcode", qr.qr_code_id)]


async def seed_and_analyze() -> None:
    from app.services import enqueue_analysis

    items = await seed_demo()
    if items:
        tasks = BackgroundTasks()
        await enqueue_analysis(items, tasks)
        await tasks()
