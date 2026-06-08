from __future__ import annotations

from typing import Any


class HTBError(Exception):
    """Base error for HTB MCP failures."""


class HTBConfigError(HTBError):
    """Raised when required local configuration is missing or invalid."""


class HTBAPIError(HTBError):
    """Raised when the HTB API returns an error response."""

    def __init__(self, status_code: int, message: str, payload: Any | None = None) -> None:
        super().__init__(f"HTB API error {status_code}: {message}")
        self.status_code = status_code
        self.message = message
        self.payload = payload
