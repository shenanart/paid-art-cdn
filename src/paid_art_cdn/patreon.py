"""Patreon OAuth2 and API v2 client."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from .settings import get_settings

PATREON_TOKEN_URL = "https://www.patreon.com/api/oauth2/token"
PATREON_IDENTITY_URL = "https://www.patreon.com/api/oauth2/v2/identity"
PATREON_AUTHORIZE_URL = "https://www.patreon.com/oauth2/authorize"

OAUTH_SCOPES = "identity identity.memberships"

_IDENTITY_PARAMS: dict[str, str] = {
    "include": "memberships,memberships.currently_entitled_tiers",
    "fields[user]": "full_name",
    "fields[member]": "patron_status,currently_entitled_amount_cents,last_charge_status",
    "fields[tier]": "title,amount_cents",
}


@dataclass
class TokenData:
    access_token: str
    refresh_token: str | None
    expires_at: datetime


@dataclass
class PatreonIdentity:
    patreon_user_id: str
    full_name: str | None
    patron_status: str | None
    tier_title: str | None
    currently_entitled_cents: float


def _parse_token_response(data: dict) -> TokenData:
    expires_in: int = data.get("expires_in", 2_678_400)  # default ~31 days
    return TokenData(
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token"),
        expires_at=datetime.now(tz=timezone.utc) + timedelta(seconds=expires_in),
    )


async def exchange_code(code: str) -> TokenData:
    """Exchange an OAuth authorization code for tokens."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            PATREON_TOKEN_URL,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "client_id": settings.patreon_client_id,
                "client_secret": settings.patreon_client_secret,
                "redirect_uri": settings.patreon_redirect_uri,
            },
        )
        resp.raise_for_status()
    return _parse_token_response(resp.json())


async def refresh_access_token(refresh_token: str) -> TokenData:
    """Use a refresh token to obtain a new access token."""
    settings = get_settings()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            PATREON_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.patreon_client_id,
                "client_secret": settings.patreon_client_secret,
            },
        )
        resp.raise_for_status()
    return _parse_token_response(resp.json())


async def get_identity(access_token: str) -> PatreonIdentity:
    """Fetch the authenticated user's identity, membership, and entitled tier."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            PATREON_IDENTITY_URL,
            params=_IDENTITY_PARAMS,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
    payload = resp.json()

    user_id: str = payload["data"]["id"]
    attrs: dict = payload["data"].get("attributes", {})
    included: list[dict] = payload.get("included", [])

    # Index included resources by type + id
    tiers_by_id = {r["id"]: r for r in included if r.get("type") == "tier"}
    members = [r for r in included if r.get("type") == "member"]

    patron_status: str | None = None
    currently_entitled_cents: float = 0.0
    tier_title: str | None = None

    if members:
        member = members[0]
        m_attrs = member.get("attributes", {})
        patron_status = m_attrs.get("patron_status", None)
        currently_entitled_cents = float(
            m_attrs.get("currently_entitled_amount_cents") or 0.0
        )

        entitled_tier_refs: list[dict] = (
            member.get("relationships", {})
            .get("currently_entitled_tiers", {})
            .get("data", [])
        )
        if entitled_tier_refs:
            tier_id = entitled_tier_refs[0]["id"]
            tier = tiers_by_id.get(tier_id)
            if tier:
                tier_title = tier.get("attributes", {}).get("title")

    return PatreonIdentity(
        patreon_user_id=user_id,
        full_name=attrs.get("full_name"),
        patron_status=patron_status,
        tier_title=tier_title,
        currently_entitled_cents=currently_entitled_cents,
    )
