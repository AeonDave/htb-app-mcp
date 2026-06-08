from __future__ import annotations

import os
from contextvars import ContextVar, Token
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

from .errors import HTBConfigError

DEFAULT_API_BASE_URL = "https://labs.hackthebox.com/api/v4"
_REQUEST_BEARER_TOKEN: ContextVar[str | None] = ContextVar(
    "htb_request_bearer_token",
    default=None,
)


@dataclass(frozen=True)
class HTBConfig:
    api_token: str
    api_base_url: str = DEFAULT_API_BASE_URL
    download_dir: Path = Path("downloads")
    timeout: float = 30.0


def set_request_bearer_token(token: str) -> Token[str | None]:
    return _REQUEST_BEARER_TOKEN.set(token)


def reset_request_bearer_token(token: Token[str | None]) -> None:
    _REQUEST_BEARER_TOKEN.reset(token)


def get_request_bearer_token() -> str | None:
    token = _REQUEST_BEARER_TOKEN.get()
    return token.strip() if token else None


def _load_dotenv_if_enabled() -> None:
    enabled = os.getenv("HTB_LOAD_DOTENV", "1").strip().lower()
    if enabled in {"0", "false", "no"}:
        return

    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        project_dotenv = Path(__file__).resolve().parent.parent / ".env"
        if project_dotenv.exists():
            load_dotenv(project_dotenv)

def load_config(api_token: str | None = None) -> HTBConfig:
    request_token = (api_token or get_request_bearer_token() or "").strip()
    _load_dotenv_if_enabled()

    token = request_token or (
        os.getenv("HTB_API_TOKEN")
        or os.getenv("API_TOKEN")
        or os.getenv("HTB_TOKEN")
        or ""
    ).strip()
    if not token:
        raise HTBConfigError("Set HTB_API_TOKEN or API_TOKEN in the environment or .env file.")

    timeout_raw = os.getenv("HTB_TIMEOUT", "30").strip()
    try:
        timeout = float(timeout_raw)
    except ValueError as exc:
        raise HTBConfigError("HTB_TIMEOUT must be a number of seconds.") from exc

    download_dir = Path(os.getenv("HTB_DOWNLOAD_DIR", "downloads")).expanduser().resolve()
    return HTBConfig(
        api_token=token,
        api_base_url=os.getenv("HTB_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/"),
        download_dir=download_dir,
        timeout=timeout,
    )
