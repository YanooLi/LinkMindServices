from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

from app.models import AnalysisStatus, RiskLevel


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invite_code: str | None = None


class PublicConfig(BaseModel):
    registration_requires_invite: bool
    demo_email: str | None
    demo_password: str | None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LinkCreate(BaseModel):
    url: HttpUrl
    alias: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,32}$")


class LinkBatchCreate(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1)


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    short_code: str
    short_url: str = ""
    original_url: str
    title: str | None
    created_at: datetime
    click_count: int
    status: AnalysisStatus
    risk_level: RiskLevel
    risk_reasons: list[str]
    category: str | None
    category_source: str | None
    analyzed_at: datetime | None


class LinkPage(BaseModel):
    items: list[LinkOut]
    next_cursor: int | None


class BatchResult(BaseModel):
    created: list[LinkOut]
    queued_for_analysis: int


class DailyClicks(BaseModel):
    day: str
    clicks: int


class LinkStats(BaseModel):
    link_id: int
    total_clicks: int
    daily: list[DailyClicks]
    top_referrers: list[dict]
