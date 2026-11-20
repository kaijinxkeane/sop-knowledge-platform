"""Content-free access log (replaces uvicorn's, which records full URLs).

Logs method, the *route template* (e.g. /api/v1/documents/{id}), status and
latency. Never the raw path or query string, which can carry search text.
"""

from __future__ import annotations

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("sop.access")


def _route_template(scope: Scope) -> str | None:
    """The matched route as a template: /api/v1/documents/{id}. None if unmatched.

    Built from the path (never the query string) with each path-parameter value
    replaced by its name, so it holds no free text even for dynamic routes.
    """
    if scope.get("route") is None:
        return None
    segments = scope["path"].split("/")
    params = {str(v): k for k, v in (scope.get("path_params") or {}).items()}
    return "/".join("{" + params[seg] + "}" if seg in params else seg for seg in segments)


class AccessLogMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        status = {"code": 500}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            template = _route_template(scope)
            log.info(
                "http_request",
                extra={
                    "fields": {
                        "method": scope.get("method"),
                        "route": template or "<unmatched>",
                        "status": status["code"],
                        "duration_ms": int((time.monotonic() - started) * 1000),
                    }
                },
            )
