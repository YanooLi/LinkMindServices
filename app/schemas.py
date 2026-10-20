"""Request/response shapes, following docs/SmartUrl-api.md."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl

USERNAME = r"^[A-Za-z0-9_.-]{3,32}$"


class RegisterIn(BaseModel):
    username: str = Field(pattern=USERNAME)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    invite_code: str | None = None


class LoginIn(BaseModel):
    username: str          # username or email
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str          # output only; validated on input


class UserOut(UserBrief):
    created_at: datetime
    first_name: str | None = None
    last_name: str | None = None
    bio: str | None = None


class UserStats(BaseModel):
    urls_created: int
    qr_codes_created: int


class ProfileOut(UserOut):
    stats: UserStats


class ProfilePatch(BaseModel):
    username: str | None = Field(default=None, pattern=USERNAME)
    email: EmailStr | None = None
    first_name: str | None = Field(default=None, max_length=80)
    last_name: str | None = Field(default=None, max_length=80)
    bio: str | None = Field(default=None, max_length=500)


class LoginOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserBrief


class AccessOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class AnalysisBrief(BaseModel):
    category: str | None
    is_safe: bool
    safety_score: float | None
    checked_at: datetime


ALIAS = r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,30}[A-Za-z0-9])?$"


class ShortenIn(BaseModel):
    target_url: HttpUrl
    title: str | None = Field(default=None, max_length=200)
    ai_enabled: bool = True
    # Optional custom back-half (linkmind.../my-link): 1-32 letters, digits or inner dashes; unique case-insensitively.
    custom_alias: str | None = Field(default=None, pattern=ALIAS)


class ShortenBatchIn(BaseModel):
    target_urls: list[HttpUrl] = Field(min_length=1)
    ai_enabled: bool = True


class UrlOut(BaseModel):
    original_url: str
    short_code: str
    short_url: str
    title: str | None
    clicks: int
    is_safe: bool
    user_id: int | None
    ai_enabled: bool
    ai_analysis: AnalysisBrief | None
    category: str | None = None
    created_at: datetime


class QrIn(BaseModel):
    target_url: HttpUrl
    title: str | None = Field(default=None, max_length=200)
    ai_enabled: bool = True
    color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    style: str = Field(default="square", pattern=r"^(square|rounded|dots)$")


class QrOut(BaseModel):
    original_url: str
    qr_code_id: str
    qr_code_url: str
    image_url: str
    title: str | None
    scans: int
    is_safe: bool
    user_id: int | None
    ai_enabled: bool
    color: str
    style: str
    ai_analysis: AnalysisBrief | None
    category: str | None = None
    created_at: datetime


class UrlHistory(BaseModel):
    page: int
    limit: int
    total: int
    urls: list[UrlOut]


class QrHistory(BaseModel):
    page: int
    limit: int
    total: int
    qrcodes: list[QrOut]


class GsbOut(BaseModel):
    is_safe: bool | None
    threat_types: list[str]


class AnalysisDetail(BaseModel):
    status: str
    category: str | None
    is_safe: bool
    safety_score: float | None
    threat_types: list[str]
    reasons: list[str]
    ai_provider: str | None
    google_safe_browsing: GsbOut
    checked_at: datetime


class AnalysisOut(BaseModel):
    short_code: str | None = None
    qr_code_id: str | None = None
    original_url: str
    analysis: AnalysisDetail | None


class ReanalyzeOut(BaseModel):
    message: str
    resource_type: str
    resource_id: str
    queued_at: datetime


class PublicConfig(BaseModel):
    registration_requires_invite: bool
    demo_username: str | None
    demo_password: str | None
