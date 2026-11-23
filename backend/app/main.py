from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError

from app import __version__
from app.api import (
    admin,
    auth,
    bookmarks,
    chat,
    classifications,
    documents,
    handovers,
    health,
    home,
    me,
    notes,
    projects,
    retention,
    reviews,
    search,
)
from app.api.access_log import AccessLogMiddleware
from app.config import get_settings
from app.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield
    from app.db.session import get_engine

    await get_engine().dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SOP & Knowledge Retention Platform",
        version=__version__,
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    for module in (
        health,
        auth,
        me,
        chat,
        documents,
        bookmarks,
        home,
        notes,
        reviews,
        handovers,
        projects,
        retention,
        search,
        classifications,
        admin,
    ):
        app.include_router(module.router, prefix="/api/v1")
    app.add_middleware(AccessLogMiddleware)

    @app.exception_handler(DBAPIError)
    async def _bad_text(request, exc: DBAPIError):
        # A NUL byte (or other text Postgres can't store) in any input: a 422, not a 500.
        if "CharacterNotInRepertoire" in type(getattr(exc, "orig", None)).__name__ or (
            "invalid byte sequence" in str(exc.orig)
        ):
            return JSONResponse(
                {"detail": "the text contains characters that can't be stored"}, status_code=422
            )
        raise exc

    return app


app = create_app()
