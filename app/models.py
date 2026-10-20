"""Relational schema: users own links; each link has an AI/security analysis and a stream of click events."""
import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisStatus(str, enum.Enum):
    pending = "pending"
    done = "done"
    failed = "failed"


class RiskLevel(str, enum.Enum):
    unknown = "unknown"
    safe = "safe"
    suspicious = "suspicious"
    malicious = "malicious"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    links: Mapped[list["Link"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (Index("ix_links_owner_created", "owner_id", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    short_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    original_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    click_count: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[AnalysisStatus] = mapped_column(Enum(AnalysisStatus, name="analysis_status"),
                                                   default=AnalysisStatus.pending)
    risk_level: Mapped[RiskLevel] = mapped_column(Enum(RiskLevel, name="risk_level"), default=RiskLevel.unknown)
    risk_reasons: Mapped[list] = mapped_column(JSON, default=list)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User] = relationship(back_populates="links")


class ClickEvent(Base):
    __tablename__ = "click_events"
    __table_args__ = (Index("ix_clicks_link_time", "link_id", "clicked_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"))
    clicked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    referrer: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
