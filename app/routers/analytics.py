"""docs/SmartUrl-api.md §6: per-resource analytics (time series, devices, countries, referrers) and the user summary."""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AnalyticsEvent, QrCode, Url, User
from app.security import get_current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])
PERIOD_DAYS = {"day": 1, "week": 7, "month": 30, "year": 365}


def _bucket(d: date, granularity: str) -> str:
    if granularity == "week":
        return (d - timedelta(days=d.weekday())).isoformat()       # Monday of that week
    if granularity == "month":
        return d.strftime("%Y-%m")
    return d.isoformat()


async def _events(session: AsyncSession, rtype: str, rid: str, since: datetime):
    rows = (await session.execute(select(AnalyticsEvent.event_date, AnalyticsEvent.device_type, AnalyticsEvent.country,
                                         AnalyticsEvent.referrer)
                                  .where(AnalyticsEvent.resource_type == rtype, AnalyticsEvent.resource_id == rid,
                                         AnalyticsEvent.event_date >= since))).all()
    return rows


def _series(rows, granularity: str, since: date, today: date, key: str) -> list[dict]:
    counts = Counter(_bucket(r.event_date.date() if isinstance(r.event_date, datetime) else r.event_date, granularity) for r in rows)
    buckets, d = [], since
    while d <= today:                       # include empty buckets so charts have a continuous axis
        b = _bucket(d, granularity)
        if not buckets or buckets[-1] != b:
            buckets.append(b)
        d += timedelta(days=1)
    return [{"date": b, key: counts.get(b, 0)} for b in buckets]


def _breakdown(values, label: str, unknown: str) -> list[dict]:
    c = Counter(v or unknown for v in values)
    return [{label: k, "count": n} for k, n in c.most_common(10)]


async def _resource_analytics(session, rtype: str, rid: str, user: User, granularity: str):
    model, col = (Url, Url.short_code) if rtype == "url" else (QrCode, QrCode.qr_code_id)
    res = await session.scalar(select(model).where(col == rid))
    if res is None or res.user_id != user.id:
        raise HTTPException(404, "Resource not found")
    today = datetime.now(timezone.utc).date()
    span = {"day": 30, "week": 7 * 12, "month": 365}[granularity]
    since = today - timedelta(days=span - 1)
    rows = await _events(session, rtype, rid, datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc))
    key = "clicks" if rtype == "url" else "scans"
    base = get_settings().public_base_url
    out = {"original_url": res.original_url, "title": res.title, "created_at": res.created_at,
           "owner": {"id": user.id, "username": user.username}, key: res.clicks if rtype == "url" else res.scans,
           f"{key[:-1]}_data": {"granularity": granularity, "daily": _series(rows, granularity, since, today, key),
                                "devices": _breakdown([r.device_type for r in rows], "type", "unknown"),
                                "countries": _breakdown([r.country for r in rows], "country", "Unknown"),
                                "referrers": _breakdown([r.referrer for r in rows], "referrer", "Direct")}}
    if rtype == "url":
        out.update(short_code=rid, short_url=f"{base}/{rid}")
    else:
        out.update(qr_code_id=rid, qr_code_url=f"{base}/qrcode/{rid}")
    return out


@router.get("/url/{short_code}")
async def url_analytics(short_code: str, granularity: str = Query("day", pattern="^(day|week|month)$"),
                        user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _resource_analytics(session, "url", short_code, user, granularity)


@router.get("/qrcode/{qr_code_id}")
async def qr_analytics(qr_code_id: str, granularity: str = Query("day", pattern="^(day|week|month)$"),
                       user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _resource_analytics(session, "qrcode", qr_code_id, user, granularity)


@router.get("/summary")
async def summary(period: str = Query("month", pattern="^(day|week|month|year)$"), start_date: date | None = None,
                  end_date: date | None = None, user: User = Depends(get_current_user),
                  session: AsyncSession = Depends(get_session)):
    end = end_date or datetime.now(timezone.utc).date()
    start = start_date or end - timedelta(days=PERIOD_DAYS[period] - 1)
    if start > end:
        raise HTTPException(422, "start_date must be on or before end_date")
    codes = (await session.scalars(select(Url.short_code).where(Url.user_id == user.id))).all()
    qids = (await session.scalars(select(QrCode.qr_code_id).where(QrCode.user_id == user.id))).all()
    lo = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    daily: dict[str, dict] = defaultdict(lambda: {"clicks": 0, "qr_scans": 0})
    devices, countries = Counter(), Counter()
    for rtype, ids, field in (("url", codes, "clicks"), ("qrcode", qids, "qr_scans")):
        if not ids:
            continue
        rows = (await session.execute(select(AnalyticsEvent.event_date, AnalyticsEvent.device_type, AnalyticsEvent.country)
                                      .where(AnalyticsEvent.resource_type == rtype, AnalyticsEvent.resource_id.in_(ids),
                                             AnalyticsEvent.event_date >= lo, AnalyticsEvent.event_date < hi))).all()
        for r in rows:
            d = r.event_date.date() if isinstance(r.event_date, datetime) else r.event_date
            daily[d.isoformat()][field] += 1
            devices[r.device_type or "unknown"] += 1
            countries[r.country or "Unknown"] += 1
    activity, d = [], start
    while d <= end:
        activity.append({"date": d.isoformat(), **daily.get(d.isoformat(), {"clicks": 0, "qr_scans": 0})})
        d += timedelta(days=1)
    top_urls = (await session.execute(select(Url.short_code, Url.original_url, Url.title, Url.clicks).where(Url.user_id == user.id)
                                      .order_by(Url.clicks.desc()).limit(5))).all()
    top_qrs = (await session.execute(select(QrCode.qr_code_id, QrCode.original_url, QrCode.title, QrCode.scans)
                                     .where(QrCode.user_id == user.id).order_by(QrCode.scans.desc()).limit(5))).all()
    return {"period": period, "start_date": start, "end_date": end, "total_urls": len(codes), "total_qrcodes": len(qids),
            "total_clicks": sum(a["clicks"] for a in activity), "total_qr_scans": sum(a["qr_scans"] for a in activity),
            "daily_activity": activity,
            "devices": [{"type": k, "count": v} for k, v in devices.most_common()],
            "countries": [{"country": k, "count": v} for k, v in countries.most_common(10)],
            "top_urls": [dict(r._mapping) for r in top_urls], "top_qrcodes": [dict(r._mapping) for r in top_qrs]}
