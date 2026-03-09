"""Patreon OAuth2 login / callback / logout routes."""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db_models import OAuthState, UserSession
from ..dependencies import create_or_update_session, get_current_session, get_db
from ..patreon import OAUTH_SCOPES, PATREON_AUTHORIZE_URL, exchange_code, get_identity
from ..settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_TTL = 600  # 10 minutes


@router.get("/login", response_model=None)
async def login(
    request: Request,
    next: str = "/",
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Begin the Patreon OAuth flow.

    Stores a CSRF `state` token in the database (not a cookie) so the
    callback validates correctly even when the Patreon mobile app intercepts
    the authorize URL via deep linking and opens the redirect_uri in a new
    browser context that has no cookies from the original session.
    """
    settings = get_settings()
    state = secrets.token_urlsafe(32)

    # Only allow redirecting back to /access/ paths to prevent open redirect
    safe_next = next if next.startswith("/access/") else "/"

    expires_at = datetime.now(tz=timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=_STATE_TTL
    )
    db.add(OAuthState(state=state, next_url=safe_next, expires_at=expires_at))
    await db.commit()

    # Opportunistically purge expired states to keep the table small
    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    await db.execute(delete(OAuthState).where(OAuthState.expires_at < now))
    await db.commit()

    logger.info(
        "OAuth login started: state=%s next_requested=%r safe_next=%r client=%s",
        state,
        next,
        safe_next,
        request.client,
    )

    params = urlencode(
        {
            "response_type": "code",
            "client_id": settings.patreon_client_id,
            "redirect_uri": settings.patreon_redirect_uri,
            "scope": OAUTH_SCOPES,
            "state": state,
        }
    )
    return RedirectResponse(url=f"{PATREON_AUTHORIZE_URL}?{params}")


@router.get("/patreon", response_model=None)
async def callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse | HTMLResponse:
    """Handle the Patreon OAuth callback.

    Validates the CSRF state against the database, exchanges the code for
    tokens, fetches the user's identity and membership, then creates/updates
    a session row and sets the session cookie.

    State is stored in the DB rather than a cookie so this works even when the
    Patreon mobile app handles the authorization natively and opens the
    redirect_uri in a fresh browser context with no cookies.
    """
    settings = get_settings()

    result = await db.execute(
        select(OAuthState).where(OAuthState.state == state)
    )
    oauth_state = result.scalar_one_or_none()

    if oauth_state is None:
        logger.warning(
            "OAuth callback: unknown or expired state. "
            "client=%s state_param=%s cookies_present=%r",
            request.client,
            state,
            list(request.cookies.keys()),
        )
        return HTMLResponse(
            "<h1>Invalid OAuth state.</h1>"
            "<p>Your login link may have expired (10-minute limit). "
            "Please <a href='/auth/login'>try again</a>.</p>",
            status_code=400,
        )

    # Consume the state — single-use to prevent replay attacks
    next_url = oauth_state.next_url
    await db.delete(oauth_state)
    await db.commit()

    now = datetime.now(tz=timezone.utc).replace(tzinfo=None)
    if oauth_state.expires_at < now:
        logger.warning(
            "OAuth callback: state expired. client=%s state_param=%s expired_at=%s",
            request.client,
            state,
            oauth_state.expires_at,
        )
        return HTMLResponse(
            "<h1>Login link expired.</h1>"
            "<p>Please <a href='/auth/login'>try again</a>.</p>",
            status_code=400,
        )

    logger.info(
        "OAuth callback: state valid. client=%s next_url=%r",
        request.client,
        next_url,
    )

    try:
        token_data = await exchange_code(code)
        identity = await get_identity(token_data.access_token)
        logger.info(
            "OAuth login success: user_id=%s name=%r"
            " patron_status=%r tier=%r entitled_cents=%s client=%s",
            identity.patreon_user_id,
            identity.full_name,
            identity.patron_status,
            identity.tier_title,
            identity.currently_entitled_cents,
            request.client,
        )
    except Exception:
        logger.exception(
            "OAuth token/identity exchange failed. client=%s code_prefix=%s",
            request.client,
            code[:8] if code else "(none)",
        )
        return HTMLResponse(
            "<h1>Patreon authentication failed.</h1>"
            "<p>Please <a href='/auth/login'>try again</a>.</p>",
            status_code=502,
        )

    session = await create_or_update_session(db, identity, token_data)

    response = RedirectResponse(url=next_url, status_code=303)
    response.set_cookie(
        "session_id",
        session.id,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return response


@router.get("/logout", response_model=None)
@router.post("/logout", response_model=None)
async def logout(
    db: AsyncSession = Depends(get_db),
    session: UserSession | None = Depends(get_current_session),
) -> RedirectResponse:
    """Delete the server-side session and clear the cookie."""
    if session is not None:
        await db.delete(session)
        await db.commit()

    response = RedirectResponse(url="https://shenan.art", status_code=303)
    response.delete_cookie("session_id")
    return response
