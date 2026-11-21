from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.api import (
    admin,
    auth,
    chat,
    classifications,
    documents,
    handovers,
    health,
    me,
    notes,
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
        notes,
        reviews,
        handovers,
        retention,
        search,
        classifications,
        admin,
    ):
        app.include_router(module.router, prefix="/api/v1")
    app.add_middleware(AccessLogMiddleware)
    return app


app = create_app()
