from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.types import ExceptionHandler

from .database import init_db
from .routers.auth_router import router as auth_router
from .routers.cdn_router import limiter
from .routers.cdn_router import router as cdn_router


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await init_db()
    yield


app = FastAPI(
    lifespan=_lifespan,
    openapi_url=None,
    redoc_url=None,
    docs_url=None,
    swagger_ui_oauth2_redirect_url=None,
)

# Attach the rate limiter and its 429 handler
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded, cast(ExceptionHandler, _rate_limit_exceeded_handler)
)

app.include_router(auth_router)
app.include_router(cdn_router)


@app.get("/")
def homepage() -> RedirectResponse:
    return RedirectResponse("https://shenan.art")
