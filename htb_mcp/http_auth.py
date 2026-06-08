from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .config import reset_request_bearer_token, set_request_bearer_token

ASGIApp = Callable[
    [dict[str, Any], Callable[[], Awaitable[dict[str, Any]]], Callable[[dict[str, Any]], Awaitable[None]]],
    Awaitable[None],
]


def _extract_bearer_token(headers: list[tuple[bytes, bytes]]) -> str | None:
    for name, value in headers:
        if name.lower() != b"authorization":
            continue
        authorization = value.decode("latin1").strip()
        if not authorization.lower().startswith("bearer "):
            return None
        token = authorization[7:].strip()
        return token or None
    return None


class HTBBearerTokenMiddleware:
    """Expose the inbound MCP HTTP Bearer token to HTB API calls."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(
        self,
        scope: dict[str, Any],
        receive: Callable[[], Awaitable[dict[str, Any]]],
        send: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        if scope.get("type") != "http":
            await self._app(scope, receive, send)
            return

        token = _extract_bearer_token(scope.get("headers", []))
        if token is None:
            await self._app(scope, receive, send)
            return

        context_token = set_request_bearer_token(token)
        try:
            await self._app(scope, receive, send)
        finally:
            reset_request_bearer_token(context_token)
