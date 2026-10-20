"""Run the full analysis for one link and persist it. Called by the RabbitMQ worker (or in-process fallback)."""
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app import cache
from app.analysis import classifier, fetcher, heuristics, safebrowsing
from app.config import get_settings
from app.models import AnalysisStatus, Link, RiskLevel

log = logging.getLogger(__name__)


async def analyze_link(session: AsyncSession, link_id: int) -> Link | None:
    s = get_settings()
    link = await session.get(Link, link_id)
    if link is None:
        return None
    try:
        reasons = heuristics.url_signals(link.original_url)
        risk = heuristics.risk_from_signals(reasons)

        threats = await safebrowsing.check(link.original_url, s.safe_browsing_api_key)
        if threats:
            risk = "malicious"
            reasons = [f"Google Safe Browsing: {t.replace('_', ' ').lower()}" for t in threats] + reasons
        elif threats is None and not s.safe_browsing_api_key:
            reasons.append("Google Safe Browsing not checked (no API key configured)")

        title = link.title
        if s.fetch_page_metadata and risk != "malicious" and not title:
            try:
                title = await fetcher.fetch_title(link.original_url)
            except fetcher.UnsafeURL as exc:
                reasons.append(f"not fetched: {exc}")
            except Exception as exc:  # network errors must not fail the whole analysis
                log.info("title fetch failed for %s: %s", link.original_url, exc)

        category, source = await classifier.classify(link.original_url, title, s)
        if category == "spam" and risk == "safe":
            risk = "suspicious"
            reasons.append("classified as spam")

        link.title = title
        link.risk_level = RiskLevel(risk)
        link.risk_reasons = [r for r in reasons if r]
        link.category, link.category_source = category, source
        link.status = AnalysisStatus.done
    except Exception:
        log.exception("analysis failed for link %s", link_id)
        link.status = AnalysisStatus.failed
    link.analyzed_at = datetime.now(timezone.utc)
    await session.commit()
    await cache.invalidate_link(link.short_code)  # the redirect path caches risk_level
    return link
