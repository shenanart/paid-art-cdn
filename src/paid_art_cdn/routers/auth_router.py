"""Patreon OAuth2 login / callback / logout routes."""

import logging
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request

logger = logging.getLogger(__name__)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..db_models import UserSession
from ..dependencies import create_or_update_session, get_current_session, get_db
from ..patreon import OAUTH_SCOPES, PATREON_AUTHORIZE_URL, exchange_code, get_identity
from ..settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])

_STATE_COOKIE = "oauth_state"
_NEXT_COOKIE = "oauth_next"
_STATE_TTL = 600  # 10 minutes


@router.get("/login", response_model=None)
async def login(request: Request, next: str = "/") -> RedirectResponse:
    """Begin the Patreon OAuth flow.

    Stores a CSRF `state` token in a short-lived cookie and redirects the
    user to Patreon's authorization page.
    """
    settings = get_settings()
    state = secrets.token_urlsafe(32)

    params = urlencode(
        {
            "response_type": "code",
            "client_id": settings.patreon_client_id,
            "redirect_uri": settings.patreon_redirect_uri,
            "scope": OAUTH_SCOPES,
            "state": state,
        }
    )
    response = RedirectResponse(url=f"{PATREON_AUTHORIZE_URL}?{params}")

    # Only allow redirecting back to /access/ paths to prevent open redirect
    safe_next = next if next.startswith("/access/") else "/"
    for key, value in ((_STATE_COOKIE, state), (_NEXT_COOKIE, safe_next)):
        response.set_cookie(
            key,
            value,
            max_age=_STATE_TTL,
            httponly=True,
            samesite="lax",
            secure=settings.cookie_secure,
        )
    return response


@router.get("/patreon", response_model=None)
async def callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse | HTMLResponse:
    """Handle the Patreon OAuth callback.

    Validates the CSRF state, exchanges the code for tokens, fetches the
    user's identity and membership, then creates/updates a session row and
    sets the session cookie.
    """
    settings = get_settings()

    stored_state = request.cookies.get(_STATE_COOKIE)
    if not stored_state or not secrets.compare_digest(stored_state, state):
        return HTMLResponse(
            "<h1>Invalid OAuth state.</h1><p>Please <a href='/auth/login'>try again</a>.</p>",
            status_code=400,
        )

    next_url = request.cookies.get(_NEXT_COOKIE, "/")

    try:
        token_data = await exchange_code(code)
        identity = await get_identity(token_data.access_token)
        print(
            f"[DEV] Patreon login: user_id={identity.patreon_user_id}"
            f" name={identity.full_name!r} email={identity.email!r}"
            f" patron_status={identity.patron_status!r}"
            f" tier={identity.tier_title!r}"
            f" entitled_cents={identity.currently_entitled_cents}",
            flush=True,
        )
    except Exception:
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
    response.delete_cookie(_STATE_COOKIE)
    response.delete_cookie(_NEXT_COOKIE)
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
