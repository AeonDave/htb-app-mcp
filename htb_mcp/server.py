from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .client import HTBClient, compact_items, find_download_url
from .config import load_config
from .errors import HTBAPIError, HTBError
from .files import (
    extract_zip_archive,
    filename_from_content_disposition,
    filename_from_url,
    write_download,
)
from .http_auth import HTBBearerTokenMiddleware

DOWNLOAD_MIN_INTERVAL_SECONDS = float(os.getenv("HTB_DOWNLOAD_MIN_INTERVAL", "1.0"))
_DOWNLOAD_LOCK = asyncio.Lock()
_last_download_started = 0.0
_shutdown_in_progress = False

mcp = FastMCP(
    "htb",
    instructions=(
        "Use these tools for the Hack The Box app platform, not ctf.hackthebox.com. "
        "Prefer search/list/detail tools before side-effect tools. "
        "Use htb_download_ovpn before VM targets that require VPN access."
    ),
)


class _BenignConnectionResetFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if (
            isinstance(exc, ConnectionResetError)
            and "_ProactorBasePipeTransport._call_connection_lost" in record.getMessage()
        ):
            return False
        return True


class _BenignShutdownNoiseFilter(logging.Filter):
    _NOISY_MESSAGES = (
        "ASGI callable returned without completing response",
    )
    _SHUTDOWN_ONLY_MESSAGES = (
        "timeout graceful shutdown exceeded",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for needle in self._NOISY_MESSAGES:
            if needle in msg:
                return False
        if _shutdown_in_progress:
            for needle in self._SHUTDOWN_ONLY_MESSAGES:
                if needle in msg:
                    return False
            exc = record.exc_info[1] if record.exc_info else None
            if isinstance(exc, asyncio.CancelledError):
                return False
        return True


SERVICE_MAP: dict[str, Any] = {
    "base_url": "https://labs.hackthebox.com/api/v4",
    "auth": "Authorization: Bearer <API_TOKEN>",
    "services": {
        "machines": [
            "GET /machine/paginated",
            "GET /machine/profile/{machineSlug}",
            "GET /machine/active",
            "POST /vm/spawn",
            "POST /vm/terminate",
            "POST /api/v5/machine/own",
        ],
        "starting_point": [
            "GET /sp/tiers/progress",
            "GET /machines/{machineId}/tasks",
            "POST /machines/{machineId}/tasks/{taskId}/flag",
        ],
        "prolabs": [
            "GET /prolabs",
            "GET /prolab/{prolabId}/overview",
            "GET /prolab/{prolabId}/machines",
            "GET /prolab/{prolabId}/flags",
            "POST /prolab/{prolabId}/flag",
        ],
        "challenges": [
            "GET /challenges",
            "GET /challenge/info/{challengeSlug}",
            "GET /challenges/{challengeId}/download_link",
            "POST /challenge/own",
            "POST /container/start",
            "POST /container/stop",
        ],
        "sherlocks": [
            "GET /sherlocks",
            "GET /sherlocks/{sherlockId}/info",
            "GET /sherlocks/{sherlockId}/download_link",
            "POST /sherlocks/{sherlockId}/tasks/{taskId}/flag",
        ],
        "fortresses": [
            "GET /fortresses",
            "GET /fortress/{fortressId}",
            "GET /fortress/{fortressId}/flags",
            "POST /fortress/{fortressId}/flag",
        ],
        "seasonal": [
            "GET /season/list",
            "GET /season/machine/active",
            "GET /season/machines/{seasonId}",
            "GET /season/rewards/{seasonId}",
            "GET /season/user/rank/{seasonId}",
            "GET /season/{players|teams}/leaderboard",
            "GET /season/{players|teams}/leaderboard/top/{seasonId}",
        ],
        "vpn": [
            "GET /connections/servers?product=labs|starting_point|fortresses|competitive",
            "GET /access/ovpnfile/{vpnId}/0",
            "GET /access/ovpnfile/{vpnId}/0/1",
        ],
    },
}


@asynccontextmanager
async def htb_client() -> Any:
    config = load_config()
    async with HTBClient(config) as client:
        yield client


def _handle_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, HTBAPIError):
        return {
            "ok": False,
            "error": error.message,
            "status_code": error.status_code,
            "payload": error.payload,
        }
    if isinstance(error, HTBError):
        return {"ok": False, "error": str(error)}
    raise error


async def _call(coro: Any) -> Any:
    try:
        return await coro
    except HTBError as exc:
        return _handle_error(exc)


def _download_result(path: Path, *, extracted_to: Path | None = None) -> dict[str, Any]:
    return {
        "ok": True,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "extracted_to": str(extracted_to) if extracted_to else None,
    }


async def _download_zip_artifact(
    *,
    link_payload: Any,
    subdir: str,
    fallback_name: str,
    extract: bool,
    password: str | None,
    overwrite: bool,
) -> dict[str, Any]:
    global _last_download_started

    config = load_config()
    url = find_download_url(link_payload)
    async with _DOWNLOAD_LOCK:
        elapsed = time.monotonic() - _last_download_started
        if elapsed < DOWNLOAD_MIN_INTERVAL_SECONDS:
            await asyncio.sleep(DOWNLOAD_MIN_INTERVAL_SECONDS - elapsed)
        _last_download_started = time.monotonic()
        async with HTBClient(config) as client:
            content, content_disposition = await client.download_url(url)

    filename = filename_from_content_disposition(
        content_disposition,
        filename_from_url(url, fallback_name),
    )
    if not filename.lower().endswith(".zip"):
        filename = f"{filename}.zip"
    archive_path = write_download(config.download_dir, subdir, filename, content, overwrite=overwrite)
    extracted_to = None
    if extract:
        extracted_to = extract_zip_archive(
            archive_path,
            config.download_dir,
            f"{subdir}/{archive_path.stem}",
            password=password,
            overwrite=overwrite,
        )
    return _download_result(archive_path, extracted_to=extracted_to)


@mcp.resource("htb://service-map", mime_type="application/json")
def service_map() -> str:
    """Read the HTB API surface used by this MCP server."""
    return json.dumps(SERVICE_MAP, indent=2)


@mcp.tool()
async def htb_whoami() -> Any:
    """Validate the API token and return the authenticated HTB account profile."""
    async with htb_client() as client:
        return await _call(client.user_info())


@mcp.tool()
async def htb_user_profile(user_id: int) -> Any:
    """Return public profile details for an HTB user id."""
    async with htb_client() as client:
        return await _call(client.user_profile(user_id))


@mcp.tool()
async def htb_connection_status(include_legacy: bool = True) -> Any:
    """Return active HTB VPN/lab connections for the authenticated account."""
    async with htb_client() as client:
        current = await _call(client.connection_status())
        if not include_legacy:
            return current
        legacy = await _call(client.legacy_user_connection_status())
        return {"current": current, "legacy_user_connection": legacy}


@mcp.tool()
async def htb_vpn_servers(product: str = "labs") -> Any:
    """List VPN servers for product: labs, starting_point, fortresses, or competitive."""
    async with htb_client() as client:
        return await _call(client.vpn_servers(product))


@mcp.tool()
async def htb_switch_vpn_server(vpn_id: int) -> Any:
    """Switch the assigned HTB VPN server to a server id returned by htb_vpn_servers."""
    async with htb_client() as client:
        return await _call(client.switch_vpn_server(vpn_id))


@mcp.tool()
async def htb_download_ovpn(
    vpn_id: int,
    protocol: str = "udp",
    filename: str | None = None,
    overwrite: bool = False,
) -> Any:
    """Download an OpenVPN profile for a VPN server id. protocol must be udp or tcp."""
    try:
        normalized = protocol.lower()
        if normalized not in {"udp", "tcp"}:
            raise HTBError("protocol must be udp or tcp.")
        path = f"/access/ovpnfile/{vpn_id}/0" if normalized == "udp" else f"/access/ovpnfile/{vpn_id}/0/1"
        config = load_config()
        async with HTBClient(config) as client:
            content, content_disposition = await client.bytes_request(path)
        final_name = filename or filename_from_content_disposition(
            content_disposition,
            f"htb-{vpn_id}-{normalized}.ovpn",
        )
        destination = write_download(config.download_dir, "ovpn", final_name, content, overwrite=overwrite)
        return _download_result(destination)
    except HTBError as exc:
        return _handle_error(exc)


@mcp.tool()
async def htb_search(query: str, target_type: str = "all", limit: int = 10) -> Any:
    """Search HTB content. target_type can be all, machines, challenges, users, or teams."""
    async with htb_client() as client:
        result = await _call(client.search(query, target_type))
    if not isinstance(result, dict) or result.get("ok") is False:
        return result
    return {
        key: compact_items(value, limit=limit) if isinstance(value, list) else value
        for key, value in result.items()
    }


@mcp.tool()
async def htb_list_machines(
    page: int = 1,
    per_page: int = 20,
    keyword: str | None = None,
    difficulty: str | None = None,
    state: str | None = None,
    status: str | None = None,
    sort_by: str | None = None,
    sort_type: str | None = None,
    todo: bool = False,
) -> Any:
    """List machines with optional filters. difficulty/state accept comma-separated values."""
    async with htb_client() as client:
        return await _call(
            client.list_machines(
                page=page,
                per_page=per_page,
                keyword=keyword,
                difficulty=difficulty,
                state=state,
                status=status,
                sort_by=sort_by,
                sort_type=sort_type,
                todo=todo,
            )
        )


@mcp.tool()
async def htb_machine_info(machine: str) -> Any:
    """Return details for a machine by id or slug/name."""
    async with htb_client() as client:
        return await _call(client.machine_profile(machine))


@mcp.tool()
async def htb_active_machine() -> Any:
    """Return the currently active spawned machine, if one exists."""
    async with htb_client() as client:
        return await _call(client.active_machine())


@mcp.tool()
async def htb_recommended_machines() -> Any:
    """Return HTB recommended machine cards."""
    async with htb_client() as client:
        return await _call(client.recommended_machines())


@mcp.tool()
async def htb_machine_tasks(machine_id: int) -> Any:
    """Return task/adventure questions for a machine when available."""
    async with htb_client() as client:
        return await _call(client.machine_tasks(machine_id))


@mcp.tool()
async def htb_spawn_machine(machine_id: int) -> Any:
    """Spawn a machine or Starting Point VM by id."""
    async with htb_client() as client:
        return await _call(client.spawn_vm(machine_id))


@mcp.tool()
async def htb_stop_machine(machine_id: int) -> Any:
    """Terminate a spawned machine or Starting Point VM by id."""
    async with htb_client() as client:
        return await _call(client.terminate_vm(machine_id))


@mcp.tool()
async def htb_extend_machine(machine_id: int) -> Any:
    """Extend the running time for a spawned machine VM by id."""
    async with htb_client() as client:
        return await _call(client.extend_vm(machine_id))


@mcp.tool()
async def htb_reset_machine(machine_id: int, mode: str = "request") -> Any:
    """Reset a machine VM. mode: request, vote, or accept_vote."""
    async with htb_client() as client:
        return await _call(client.reset_vm(machine_id, mode))


@mcp.tool()
async def htb_submit_machine_flag(
    machine_id: int,
    flag: str,
    difficulty: int | None = None,
) -> Any:
    """Submit a user/root machine flag for a machine id."""
    async with htb_client() as client:
        return await _call(client.submit_machine_flag(machine_id, flag, difficulty))


@mcp.tool()
async def htb_list_challenges(
    page: int = 1,
    per_page: int = 20,
    keyword: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    state: str | None = None,
    status: str | None = None,
    sort_by: str | None = None,
    sort_type: str | None = None,
    todo: bool = False,
) -> Any:
    """List challenges. difficulty/status accept friendly aliases; category accepts comma-separated ids."""
    async with htb_client() as client:
        return await _call(
            client.list_challenges(
                page=page,
                per_page=per_page,
                keyword=keyword,
                difficulty=difficulty,
                category=category,
                state=state,
                status=status,
                sort_by=sort_by,
                sort_type=sort_type,
                todo=todo,
            )
        )


@mcp.tool()
async def htb_challenge_info(challenge: str) -> Any:
    """Return challenge details by id or slug/name."""
    async with htb_client() as client:
        return await _call(client.challenge_info(challenge))


@mcp.tool()
async def htb_challenge_categories() -> Any:
    """List challenge categories and ids useful for filtering."""
    async with htb_client() as client:
        return await _call(client.challenge_categories())


@mcp.tool()
async def htb_download_challenge(
    challenge_id: int,
    extract: bool = True,
    password: str | None = "hackthebox",
    overwrite: bool = False,
) -> Any:
    """Download a challenge ZIP by id and optionally extract it under the download directory."""
    try:
        async with htb_client() as client:
            link_payload = await client.challenge_download_link(challenge_id)
        return await _download_zip_artifact(
            link_payload=link_payload,
            subdir=f"challenges/{challenge_id}",
            fallback_name=f"challenge-{challenge_id}.zip",
            extract=extract,
            password=password,
            overwrite=overwrite,
        )
    except HTBError as exc:
        return _handle_error(exc)


@mcp.tool()
async def htb_start_challenge(challenge_id: int) -> Any:
    """Start a challenge container by challenge id when the challenge supports containers."""
    async with htb_client() as client:
        return await _call(client.start_challenge(challenge_id))


@mcp.tool()
async def htb_stop_challenge(challenge_id: int) -> Any:
    """Stop a challenge container by challenge id."""
    async with htb_client() as client:
        return await _call(client.stop_challenge(challenge_id))


@mcp.tool()
async def htb_start_container(container_id: int) -> Any:
    """Start a container by container id for HTB content that exposes one."""
    async with htb_client() as client:
        return await _call(client.start_container(container_id))


@mcp.tool()
async def htb_stop_container(container_id: int) -> Any:
    """Stop a container by container id for HTB content that exposes one."""
    async with htb_client() as client:
        return await _call(client.stop_container(container_id))


@mcp.tool()
async def htb_submit_challenge_flag(challenge_id: int, flag: str) -> Any:
    """Submit a challenge flag."""
    async with htb_client() as client:
        return await _call(client.submit_challenge_flag(challenge_id, flag))


@mcp.tool()
async def htb_list_sherlocks(
    page: int = 1,
    per_page: int = 20,
    keyword: str | None = None,
    difficulty: str | None = None,
    category: str | None = None,
    state: str | None = None,
    status: str | None = None,
    sort_by: str | None = None,
    sort_type: str | None = None,
) -> Any:
    """List Sherlocks with optional filters. category accepts comma-separated ids."""
    async with htb_client() as client:
        return await _call(
            client.list_sherlocks(
                page=page,
                per_page=per_page,
                keyword=keyword,
                difficulty=difficulty,
                category=category,
                state=state,
                status=status,
                sort_by=sort_by,
                sort_type=sort_type,
            )
        )


@mcp.tool()
async def htb_sherlock_info(sherlock: str) -> Any:
    """Return Sherlock details by id or slug/name."""
    async with htb_client() as client:
        return await _call(client.sherlock_info(sherlock))


@mcp.tool()
async def htb_sherlock_tasks(sherlock_id: int) -> Any:
    """Return tasks/questions for a Sherlock id."""
    async with htb_client() as client:
        return await _call(client.sherlock_tasks(sherlock_id))


@mcp.tool()
async def htb_sherlock_progress(sherlock_id: int) -> Any:
    """Return progress for a Sherlock id."""
    async with htb_client() as client:
        return await _call(client.sherlock_progress(sherlock_id))


@mcp.tool()
async def htb_sherlock_play(sherlock_id: int) -> Any:
    """Start or continue a Sherlock play session when supported by HTB."""
    async with htb_client() as client:
        return await _call(client.sherlock_play(sherlock_id))


@mcp.tool()
async def htb_download_sherlock(
    sherlock_id: int,
    extract: bool = True,
    password: str | None = "hackthebox",
    overwrite: bool = False,
) -> Any:
    """Download a Sherlock ZIP by id and optionally extract it under the download directory."""
    try:
        async with htb_client() as client:
            link_payload = await client.sherlock_download_link(sherlock_id)
        return await _download_zip_artifact(
            link_payload=link_payload,
            subdir=f"sherlocks/{sherlock_id}",
            fallback_name=f"sherlock-{sherlock_id}.zip",
            extract=extract,
            password=password,
            overwrite=overwrite,
        )
    except HTBError as exc:
        return _handle_error(exc)


@mcp.tool()
async def htb_submit_sherlock_task_flag(sherlock_id: int, task_id: int, flag: str) -> Any:
    """Submit the flag/answer for a Sherlock task id."""
    async with htb_client() as client:
        return await _call(client.submit_sherlock_task_flag(sherlock_id, task_id, flag))


@mcp.tool()
async def htb_list_fortresses() -> Any:
    """List HTB fortresses."""
    async with htb_client() as client:
        return await _call(client.list_fortresses())


@mcp.tool()
async def htb_fortress_info(fortress_id: int) -> Any:
    """Return details for a fortress id."""
    async with htb_client() as client:
        return await _call(client.fortress_info(fortress_id))


@mcp.tool()
async def htb_fortress_flags(fortress_id: int) -> Any:
    """List flag metadata for a fortress id."""
    async with htb_client() as client:
        return await _call(client.fortress_flags(fortress_id))


@mcp.tool()
async def htb_submit_fortress_flag(fortress_id: int, flag: str) -> Any:
    """Submit a fortress flag."""
    async with htb_client() as client:
        return await _call(client.submit_fortress_flag(fortress_id, flag))


@mcp.tool()
async def htb_reset_fortress(fortress_id: int) -> Any:
    """Vote to reset a fortress instance."""
    async with htb_client() as client:
        return await _call(client.reset_fortress(fortress_id))


@mcp.tool()
async def htb_list_seasons() -> Any:
    """List HTB seasonal machine seasons and their active/ended state."""
    async with htb_client() as client:
        return await _call(client.list_seasons())


@mcp.tool()
async def htb_active_season_machine() -> Any:
    """Return the currently active seasonal machine card."""
    async with htb_client() as client:
        return await _call(client.active_season_machine())


@mcp.tool()
async def htb_season_machines(season_id: int) -> Any:
    """List machines for a season id returned by htb_list_seasons."""
    async with htb_client() as client:
        return await _call(client.season_machines(season_id))


@mcp.tool()
async def htb_season_rewards(season_id: int) -> Any:
    """List rewards and rank progression data for a season id."""
    async with htb_client() as client:
        return await _call(client.season_rewards(season_id))


@mcp.tool()
async def htb_season_user_rank(season_id: int) -> Any:
    """Return the authenticated user's rank/progress for a season id."""
    async with htb_client() as client:
        return await _call(client.season_user_rank(season_id))


@mcp.tool()
async def htb_season_user_ranks(user_id: int) -> Any:
    """Return all seasonal ranks for a specific HTB user id."""
    async with htb_client() as client:
        return await _call(client.season_user_ranks(user_id))


@mcp.tool()
async def htb_season_leaderboard(leaderboard: str = "players", season_id: int | None = None) -> Any:
    """Return a seasonal leaderboard. leaderboard must be players or teams."""
    async with htb_client() as client:
        return await _call(client.season_leaderboard(leaderboard, season_id))


@mcp.tool()
async def htb_season_top_leaderboard(
    season_id: int,
    leaderboard: str = "players",
    period: str = "1W",
) -> Any:
    """Return top seasonal leaderboard entries. period: 1Y, 6M, 3M, 1M, or 1W."""
    async with htb_client() as client:
        return await _call(client.season_top_leaderboard(leaderboard, season_id, period))


@mcp.tool()
async def htb_starting_point_progress() -> Any:
    """Return Starting Point tier progress for the authenticated account."""
    async with htb_client() as client:
        return await _call(client.starting_point_progress())


@mcp.tool()
async def htb_starting_point_tier(tier_id: int) -> Any:
    """Return metadata for a Starting Point tier id.

    HTB removed the per-tier machine listing endpoint, so only tier metadata
    (name, description, completion) is returned. Use htb_search or
    htb_list_machines + htb_machine_info for Starting Point machine details.
    """
    async with htb_client() as client:
        return await _call(client.starting_point_tier(tier_id))


@mcp.tool()
async def htb_submit_machine_task(machine_id: int, task_id: int, flag: str) -> Any:
    """Submit the text answer/flag for a Starting Point machine task.

    Use htb_machine_tasks to list available tasks and their ids for a machine.
    Returns 'Task flag owned!' on success.
    """
    async with htb_client() as client:
        return await _call(client.submit_machine_task_flag(machine_id, task_id, flag))


@mcp.tool()
async def htb_list_prolabs() -> Any:
    """List all HTB Pro Labs with id, name, version, and subscription state."""
    async with htb_client() as client:
        return await _call(client.list_prolabs())


@mcp.tool()
async def htb_prolab_overview(prolab_id: int) -> Any:
    """Return detailed overview for a Pro Lab id (machines count, flags count, social links)."""
    async with htb_client() as client:
        return await _call(client.prolab_overview(prolab_id))


@mcp.tool()
async def htb_prolab_machines(prolab_id: int) -> Any:
    """List machines in a Pro Lab by id."""
    async with htb_client() as client:
        return await _call(client.prolab_machines(prolab_id))


@mcp.tool()
async def htb_prolab_flags(prolab_id: int) -> Any:
    """List flags for a Pro Lab by id."""
    async with htb_client() as client:
        return await _call(client.prolab_flags(prolab_id))


@mcp.tool()
async def htb_submit_prolab_flag(prolab_id: int, flag: str) -> Any:
    """Submit a flag for a Pro Lab by id."""
    async with htb_client() as client:
        return await _call(client.submit_prolab_flag(prolab_id, flag))


@mcp.tool()
async def htb_api_get(path: str, params_json: str = "{}") -> Any:
    """Call a read-only HTB API path for endpoint discovery. Example path: /machine/recommended.

    Defaults to API v4. Prefix the path with /api/vN (e.g. /api/v5/...) to target
    another version.
    """
    async with htb_client() as client:
        return await _call(client.raw_get(path, params_json))


@mcp.tool()
async def htb_api_post(path: str, body_json: str = "{}") -> Any:
    """Call a write HTB API path for endpoint discovery or ad-hoc mutations.

    Defaults to API v4. Prefix the path with /api/vN to target another version.
    Example: path=/api/v5/machine/own body_json={"id":395,"flag":"abc"}
    """
    async with htb_client() as client:
        return await _call(client.raw_post(path, body_json))


@mcp.prompt()
def htb_target_workflow(target_name: str, target_type: str = "machine") -> str:
    """Create a concise workflow prompt for working on HTB content through this MCP."""
    return (
        f"Use the HTB MCP tools for the {target_type} named {target_name}. "
        "First search and fetch details, then check VPN/connection requirements, "
        "download any required artifact or OVPN, and only then use side-effect tools "
        "such as spawn/start/submit when the user asks."
    )


def _bool_from_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_from_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value.strip())
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


def _configure_logging() -> None:
    if _bool_from_env("HTB_MCP_VERBOSE_HTTP"):
        return
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("mcp.server.streamable_http").setLevel(logging.WARNING)
    logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)
    logging.getLogger("asyncio").addFilter(_BenignConnectionResetFilter())
    shutdown_filter = _BenignShutdownNoiseFilter()
    for logger_name in ("uvicorn.error", "uvicorn", "asyncio"):
        logging.getLogger(logger_name).addFilter(shutdown_filter)


def _configure_windows_event_loop() -> None:
    if sys.platform != "win32":
        return
    if not _bool_from_env("HTB_MCP_WINDOWS_SELECTOR_EVENT_LOOP", default=True):
        return
    policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if policy is not None:
        asyncio.set_event_loop_policy(policy())


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hack The Box MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "streamable-http"),
        default=os.getenv("HTB_MCP_TRANSPORT", "stdio"),
        help="stdio for local launch, http/streamable-http for URL-based MCP clients.",
    )
    parser.add_argument("--host", default=os.getenv("HTB_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("HTB_MCP_PORT", "8000")))
    parser.add_argument("--path", default=os.getenv("HTB_MCP_PATH", "/mcp"))
    parser.add_argument(
        "--stateless-http",
        action="store_true",
        default=None,
        help="Run Streamable HTTP without server-side MCP session state.",
    )
    parser.add_argument(
        "--stateful-http",
        action="store_true",
        default=False,
        help="Keep server-side MCP HTTP sessions. Not restart-resilient; mainly for debugging protocol behavior.",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        default=_bool_from_env("HTB_MCP_JSON_RESPONSE"),
        help="Return JSON responses instead of SSE streams where supported.",
    )
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        default=os.getenv("HTB_MCP_LOG_LEVEL", "INFO"),
    )
    parser.add_argument(
        "--graceful-shutdown-timeout",
        type=int,
        default=_int_from_env("HTB_MCP_GRACEFUL_SHUTDOWN_TIMEOUT", 5),
        help="Maximum seconds uvicorn waits for open HTTP streams during Ctrl+C shutdown.",
    )
    args = parser.parse_args()
    if args.stateful_http:
        args.stateless_http = False
    elif args.stateless_http is None:
        args.stateless_http = _bool_from_env("HTB_MCP_STATELESS_HTTP", default=True)
    if args.graceful_shutdown_timeout < 1:
        parser.error("--graceful-shutdown-timeout must be at least 1 second.")
    return args


def _run_http_server(args: argparse.Namespace) -> None:
    import uvicorn

    mcp.settings.host = args.host
    mcp.settings.port = args.port
    mcp.settings.streamable_http_path = args.path
    mcp.settings.stateless_http = args.stateless_http
    mcp.settings.json_response = args.json_response
    mcp.settings.log_level = args.log_level

    app = mcp.streamable_http_app()
    app.add_middleware(HTBBearerTokenMiddleware)

    class ShutdownAwareServer(uvicorn.Server):
        def handle_exit(self, sig: int, frame: Any | None) -> None:
            global _shutdown_in_progress
            _shutdown_in_progress = True
            super().handle_exit(sig, frame)

        async def shutdown(self, sockets: list[Any] | None = None) -> None:
            global _shutdown_in_progress
            _shutdown_in_progress = True
            await super().shutdown(sockets)

    config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
        timeout_graceful_shutdown=args.graceful_shutdown_timeout,
    )
    server = ShutdownAwareServer(config)
    try:
        server.run()
    except KeyboardInterrupt:
        global _shutdown_in_progress
        _shutdown_in_progress = True
        logging.getLogger(__name__).info("Shutdown requested (Ctrl+C).")


def main() -> None:
    _configure_windows_event_loop()
    _configure_logging()
    args = _parse_args()
    if args.transport == "stdio":
        mcp.run(transport="stdio")
        return
    try:
        _run_http_server(args)
    except KeyboardInterrupt:
        global _shutdown_in_progress
        _shutdown_in_progress = True
        logging.getLogger(__name__).info("Shutdown requested (Ctrl+C).")


if __name__ == "__main__":
    main()
