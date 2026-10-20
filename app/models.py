"""Relational schema, following docs/SmartUrl-database-schema.md (Sui Yeung's design).

users ─┬─< urls       (user_id ON DELETE SET NULL: links keep working after the account is deleted)
       └─< qrcodes
ai_analyses: one row per resource (resource_type, resource_id) — 'url'/'qrcode' + short_code/qr_code_id
analytics:   one row per click or scan event, with device type, country and referrer
"""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (Index("idx_auth_provider", "auth_provider", "auth_provider_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(Text, unique=True)
    email: Mapped[str] = mapped_column(Text, unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)        # NULL for OAuth users
    auth_provider: Mapped[str | None] = mapped_column(Text, nullable=True)       # NULL = local, "google" later
    auth_provider_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)          # Settings › Profile
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Url(Base):
    __tablename__ = "urls"
    __table_args__ = (Index("idx_urls_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_url: Mapped[str] = mapped_column(Text)
    short_code: Mapped[str] = mapped_column(Text, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    is_safe: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)              # Create Link › "Enable AI Analysis"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QrCode(Base):
    __tablename__ = "qrcodes"
    __table_args__ = (Index("idx_qrcodes_user", "user_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    original_url: Mapped[str] = mapped_column(Text)
    qr_code_id: Mapped[str] = mapped_column(Text, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    scans: Mapped[int] = mapped_column(Integer, default=0)
    is_safe: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    color: Mapped[str] = mapped_column(String(7), default="#000000")             # QR Generator › Brand color
    style: Mapped[str] = mapped_column(String(16), default="square")             # QR Generator › QR style
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiAnalysis(Base):
    __tablename__ = "ai_analyses"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_id"),
        Index("idx_ai_resource", "resource_type", "resource_id"),
        Index("idx_ai_is_safe", "is_safe"),
        Index("idx_ai_category", "category"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_type: Mapped[str] = mapped_column(Text)            # "url" | "qrcode"
    resource_id: Mapped[str] = mapped_column(Text)              # short_code | qr_code_id
    status: Mapped[str] = mapped_column(Text, default="pending")  # pending | done | failed
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_safe: Mapped[bool] = mapped_column(Boolean, default=True)
    safety_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    threat_types: Mapped[list] = mapped_column(JSON, default=list)   # TEXT[] in the design; JSON keeps SQLite tests working
    reasons: Mapped[list] = mapped_column(JSON, default=list)        # human-readable explanation of the score
    ai_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_safe_browsing_safe: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    google_safe_browsing_threats: Mapped[list] = mapped_column(JSON, default=list)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalyticsEvent(Base):
    __tablename__ = "analytics"
    __table_args__ = (
        Index("idx_resource", "resource_type", "resource_id"),
        Index("idx_event_date", "event_date"),
        Index("idx_device_type", "device_type"),
        Index("idx_country", "country"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resource_type: Mapped[str] = mapped_column(Text)
    resource_id: Mapped[str] = mapped_column(Text)
    event_type: Mapped[str] = mapped_column(Text)               # "click" | "scan"
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    device_type: Mapped[str | None] = mapped_column(Text, nullable=True)   # desktop | mobile | tablet
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    referrer: Mapped[str | None] = mapped_column(Text, nullable=True)      # Analytics › Top Referrers (host only)
