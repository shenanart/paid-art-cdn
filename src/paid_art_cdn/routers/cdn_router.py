"""Protected file-delivery route."""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from ..dependencies import get_current_session, get_db
from ..db_models import UserSession
from ..settings import get_settings

router = APIRouter(tags=["cdn"])

_TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Module-level limiter — registered on the app in __init__.py
limiter = Limiter(key_func=get_remote_address)


def _safe_file_path(file_name: str) -> Path | None:
    """Resolve the requested filename within files_dir.

    Returns None if the name contains path-traversal components or the
    resolved path escapes the configured files directory.
    """
    settings = get_settings()
    # Reject anything that isn't a plain filename (no slashes, no '..')
    requested = Path(file_name)
    if requested != Path(requested.name) or ".." in requested.parts:
        return None

    files_dir = Path(settings.files_dir).resolve()
    target = (files_dir / requested.name).resolve()

    # Double-check the resolved path is still inside files_dir
    if not target.is_relative_to(files_dir):
        return None

    return target


_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".avi", ".mkv", ".m4v", ".ogv"}


def _is_video(file_name: str) -> bool:
    return Path(file_name).suffix.lower() in _VIDEO_EXTENSIONS


async def _check_access(
    request: Request,
    file_name: str,
    session: UserSession | None,
):
    """Shared auth check. Returns a response on failure, None on success."""
    if session is None:
        return RedirectResponse(url=f"/auth/login?next=/access/{file_name}")

    settings = get_settings()
    allowed_tiers = {t.strip() for t in settings.paid_tier.split(",")}

    if session.patron_status != "active_patron":
        print(f"[DEV] 403: patron_status={session.patron_status!r} (not active_patron)", flush=True)
        return templates.TemplateResponse(
            request,
            "unauthorized.html",
            {"full_name": session.full_name},
            status_code=403,
        )

    if session.tier_title not in allowed_tiers:
        print(f"[DEV] 403: tier={session.tier_title!r} not in allowed={allowed_tiers}", flush=True)
        return templates.TemplateResponse(
            request,
            "wrong_tier.html",
            {
                "full_name": session.full_name,
                "tier_title": session.tier_title,
                "required_tiers": sorted(allowed_tiers),
            },
            status_code=403,
        )

    return None


@router.get("/access/{file_name}")
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
async def access_file(
    request: Request,
    file_name: str,
    db: AsyncSession = Depends(get_db),
    session: UserSession | None = Depends(get_current_session),
):
    """Show the viewer page for a protected file."""
    denied = await _check_access(request, file_name, session)
    if denied is not None:
        return denied

    target = _safe_file_path(file_name)
    if target is None or not target.exists():
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "File not found."},
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "viewer.html",
        {"file_name": file_name, "is_video": _is_video(file_name)},
    )


@router.get("/stream/{file_name}")
@limiter.limit(lambda: f"{get_settings().rate_limit_per_minute}/minute")
async def stream_file(
    request: Request,
    file_name: str,
    db: AsyncSession = Depends(get_db),
    session: UserSession | None = Depends(get_current_session),
):
    """Deliver the raw file bytes after validating the user's Patreon membership."""
    denied = await _check_access(request, file_name, session)
    if denied is not None:
        return denied

    target = _safe_file_path(file_name)
    if target is None or not target.exists():
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": "File not found."},
            status_code=404,
        )

    return FileResponse(target)
