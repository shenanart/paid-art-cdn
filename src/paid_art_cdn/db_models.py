import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc).replace(tzinfo=None)


class OAuthState(Base):
    """Short-lived CSRF state tokens for the Patreon OAuth flow.

    Stored in the database rather than a cookie so the callback validates
    correctly regardless of which browser context Patreon redirects into
    (e.g. when the Patreon mobile app intercepts the authorize URL via deep
    linking and opens the redirect_uri in a new tab or WebView).
    """

    __tablename__ = "oauth_states"

    state: Mapped[str] = mapped_column(String, primary_key=True)
    next_url: Mapped[str] = mapped_column(String, default="/")
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    patreon_user_id: Mapped[str] = mapped_column(String, index=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Patreon OAuth tokens
    access_token: Mapped[str] = mapped_column(String)
    refresh_token: Mapped[str | None] = mapped_column(String, nullable=True)
    # When the Patreon access_token expires (~31 days after issue)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Cached membership state (refreshed on token renewal)
    patron_status: Mapped[str | None] = mapped_column(String, nullable=True)
    tier_title: Mapped[str | None] = mapped_column(String, nullable=True)
    currently_entitled_cents: Mapped[float] = mapped_column(Float, default=0.0)

    # Session lifetime (7-day TTL, independent of token expiry)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
