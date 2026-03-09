"""FastAPI dependency providers for DB sessions and user sessions."""

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import patreon as patreon_client
from .database import AsyncSessionLocal
from .db_models import UserSession

SESSION_TTL_DAYS = 7
# Refresh the Patreon access token if it expires within this window
TOKEN_REFRESH_BUFFER = timedelta(hours=1)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def _refresh_token_if_needed(
    session: UserSession, db: AsyncSession
) -> UserSession:
    """Silently refresh the Patreon access token when it's near expiry.

    Also re-fetches membership data so patron_status/tier stay current.
    If the refresh fails the existing token is kept until the session expires.
    """
    now = datetime.now(tz=timezone.utc)
    token_exp = session.token_expires_at
    if token_exp and token_exp.tzinfo is None:
        token_exp = token_exp.replace(tzinfo=timezone.utc)

    needs_refresh = (
        session.refresh_token is not None
        and token_exp is not None
        and now >= token_exp - TOKEN_REFRESH_BUFFER
    )
    if not needs_refresh:
        return session

    try:
        token_data = await patreon_client.refresh_access_token(session.refresh_token)  # type: ignore[arg-type]
        # Re-fetch identity so membership/tier data stays fresh
        identity = await patreon_client.get_identity(token_data.access_token)

        session.access_token = token_data.access_token
        if token_data.refresh_token:
            session.refresh_token = token_data.refresh_token
        session.token_expires_at = token_data.expires_at.replace(tzinfo=None)
        session.patron_status = identity.patron_status
        session.tier_title = identity.tier_title
        session.currently_entitled_cents = identity.currently_entitled_cents

        db.add(session)
        await db.commit()
        await db.refresh(session)
    except Exception:
        # Refresh failed — keep current token; session will expire naturally
        pass

    return session


async def get_current_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserSession | None:
    """Return the active UserSession for this request, or None."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        return None

    result = await db.execute(
        select(UserSession).where(UserSession.id == session_id)
    )
    session = result.scalar_one_or_none()

    if session is None:
        return None

    now = datetime.now(tz=timezone.utc)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= now:
        return None

    return await _refresh_token_if_needed(session, db)


async def create_or_update_session(
    db: AsyncSession,
    identity: patreon_client.PatreonIdentity,
    token_data: patreon_client.TokenData,
) -> UserSession:
    """Upsert a UserSession row and return it."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.patreon_user_id == identity.patreon_user_id
        )
    )
    session = result.scalar_one_or_none()

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)

    if session is None:
        session = UserSession(id=str(uuid.uuid4()))
        session.patreon_user_id = identity.patreon_user_id
        session.created_at = now

    session.full_name = identity.full_name
    session.access_token = token_data.access_token
    session.refresh_token = token_data.refresh_token
    session.token_expires_at = token_data.expires_at.replace(tzinfo=None)
    session.patron_status = identity.patron_status
    session.tier_title = identity.tier_title
    session.currently_entitled_cents = identity.currently_entitled_cents
    session.expires_at = now + timedelta(days=SESSION_TTL_DAYS)

    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session
