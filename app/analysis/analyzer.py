"""Analyze one resource (short URL or QR code) and store the result in ai_analyses (docs/SmartUrl-api.md, AI Analysis
Pipeline): Google Safe Browsing check → URL heuristics → optional AI classification → composite safety score →
store, flag the resource (is_safe) and invalidate its cache entry. Called by the RabbitMQ worker or in-process."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.analysis import classifier, fetcher, heuristics, safebrowsing
from app.config import get_settings
from app.models import AiAnalysis, QrCode, Url

log = logging.getLogger(__name__)


async def load_resource(session: AsyncSession, resource_type: str, resource_id: str):
    if resource_type == "url":
        return await session.scalar(select(Url).where(Url.short_code == resource_id))
    return await session.scalar(select(QrCode).where(QrCode.qr_code_id == resource_id))


async def get_or_create_analysis(session: AsyncSession, resource_type: str, resource_id: str) -> AiAnalysis:
    row = await session.scalar(select(AiAnalysis).where(AiAnalysis.resource_type == resource_type,
                                                        AiAnalysis.resource_id == resource_id))
    if row is None:
        row = AiAnalysis(resource_type=resource_type, resource_id=resource_id, status="pending")
        session.add(row)
    return row


async def analyze_resource(session: AsyncSession, resource_type: str, resource_id: str) -> AiAnalysis | None:
    s = get_settings()
    res = await load_resource(session, resource_type, resource_id)
    if res is None:
        return None
    row = await get_or_create_analysis(session, resource_type, resource_id)
    try:
        url = res.original_url
        threats = await safebrowsing.check(url, s.safe_browsing_api_key)
        reasons = heuristics.url_signals(url)
        score, tags = heuristics.score_signals(reasons)
        if threats:
            score, tags = 0.0, [t.lower() for t in threats] + tags
            reasons = [f"Google Safe Browsing: {t.replace('_', ' ').lower()}" for t in threats] + reasons
        elif threats is None:
            reasons.append("Google Safe Browsing not checked (no API key configured)")

        if not res.title and s.fetch_page_metadata and score > 0:
            try:
                res.title = await fetcher.fetch_title(url)
            except fetcher.UnsafeURL as exc:
                reasons.append(f"title not fetched: {exc}")
            except Exception as exc:  # network errors must not fail the analysis
                log.info("title fetch failed for %s: %s", url, exc)

        category, provider = None, None
        if res.ai_enabled:
            category, provider = await classifier.classify(url, res.title, s)
            if category == "spam":
                score = max(0.0, round(score - 0.3, 2))
                tags.append("spam")
                reasons.append("classified as spam")

        row.category, row.ai_provider = category, provider
        row.safety_score = score
        row.is_safe = score >= s.safety_threshold
        row.threat_types = sorted(set(tags))
        row.reasons = reasons
        row.google_safe_browsing_safe = None if threats is None else not threats
        row.google_safe_browsing_threats = threats or []
        row.status = "done"
        res.is_safe = row.is_safe
    except Exception:
        log.exception("analysis failed for %s %s", resource_type, resource_id)
        row.status = "failed"
    row.analyzed_at = datetime.now(timezone.utc)
    await session.commit()
    await cache.invalidate(resource_type, resource_id)
    return row
