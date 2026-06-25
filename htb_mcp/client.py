from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any
from urllib.parse import urlparse

import httpx

from .config import HTBConfig
from .errors import HTBAPIError, HTBError

JsonMap = dict[str, Any]
QueryParams = Mapping[str, Any] | None


def compact_items(items: Iterable[Mapping[str, Any]], *, limit: int = 10) -> list[JsonMap]:
    compacted: list[JsonMap] = []
    for item in list(items)[:limit]:
        compacted.append(
            {
                key: item.get(key)
                for key in (
                    "id",
                    "name",
                    "value",
                    "difficulty",
                    "difficultyText",
                    "os",
                    "state",
                    "category_name",
                    "type",
                    "ip",
                    "ports",
                    "is_owned",
                    "authUserSolve",
                    "authUserInUserOwns",
                    "authUserInRootOwns",
                    "playInfo",
                    "play_info",
                )
                if key in item
            }
        )
    return compacted


def parse_params_json(params_json: str) -> JsonMap:
    try:
        value = json.loads(params_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTBError("params_json must be a JSON object string.") from exc
    if not isinstance(value, dict):
        raise HTBError("params_json must decode to a JSON object.")
    return value


# Matches an "/api/vN" version segment at the start of a path or anywhere in a
# base URL (e.g. "/api/v4", "/api/v5").
_API_VERSION_RE = re.compile(r"/api/(v\d+)")


def resolve_api_path(path: str) -> tuple[str | None, str]:
    """Split an HTB API path into ``(api_version, path)``.

    ``api_version`` is the explicit version a caller pinned -- via a full
    ``labs.hackthebox.com`` URL or an ``/api/vN/...`` prefix (e.g. ``"v5"``) --
    or ``None`` to use the client's configured default version. The returned
    path always starts with ``/`` and is the version-stripped, traversal-checked
    remainder so it can be joined to whichever versioned base is selected.
    """
    raw = path.strip()
    if not raw:
        raise HTBError("API path cannot be empty.")

    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        if parsed.netloc != "labs.hackthebox.com":
            raise HTBError("Only labs.hackthebox.com URLs are accepted.")
        if parsed.query:
            raise HTBError("Put query parameters in params_json, not in the path.")
        raw = parsed.path

    version: str | None = None
    version_match = re.match(r"^/api/(v\d+)(/.*)?$", raw)
    if version_match:
        version = version_match.group(1)
        raw = version_match.group(2) or "/"

    if not raw.startswith("/"):
        raw = f"/{raw}"
    if any(segment == ".." for segment in raw.split("/")):
        raise HTBError("Path traversal segments are not allowed.")
    return version, raw


def normalize_api_path(path: str) -> str:
    """Return the version-stripped path part of an HTB API path."""
    return resolve_api_path(path)[1]


def detect_base_version(base_url: str) -> str | None:
    """Return the ``vN`` version embedded in a base URL, if any."""
    match = _API_VERSION_RE.search(base_url)
    return match.group(1) if match else None


def base_url_for_version(base_url: str, version: str) -> str:
    """Return ``base_url`` rewritten to target the given ``/api/vN`` version."""
    rewritten, count = _API_VERSION_RE.subn(f"/api/{version}", base_url, count=1)
    if count:
        return rewritten
    return f"{base_url.rstrip('/')}/api/{version}"


def find_download_url(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("url", "download_url", "downloadUrl", "link"):
            value = payload.get(key)
            if isinstance(value, str) and value.startswith(("http://", "https://")):
                return value
        for value in payload.values():
            try:
                return find_download_url(value)
            except HTBError:
                continue
    if isinstance(payload, list):
        for value in payload:
            try:
                return find_download_url(value)
            except HTBError:
                continue
    raise HTBError("Could not find a download URL in the HTB response.")


def csv_values(value: str | None) -> list[str] | None:
    if value is None or not value.strip():
        return None
    return [part.strip() for part in value.split(",") if part.strip()]


def int_csv_values(value: str | None) -> list[int] | None:
    values = csv_values(value)
    if values is None:
        return None
    try:
        return [int(part) for part in values]
    except ValueError as exc:
        raise HTBError("Expected comma-separated integers.") from exc


def add_if_present(params: JsonMap, key: str, value: Any | None) -> None:
    if value is not None and value != "":
        params[key] = value


def validate_choice(value: str, allowed: set[str], field_name: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        expected = ", ".join(sorted(allowed))
        raise HTBError(f"{field_name} must be one of: {expected}.")
    return normalized


DIFFICULTY_ALIASES = {
    "very easy": "very-easy",
    "very_easy": "very-easy",
    "very-easy": "very-easy",
    "easy": "easy",
    "medium": "medium",
    "hard": "hard",
    "insane": "insane",
}

STATUS_ALIASES = {
    "complete": "complete",
    "completed": "complete",
    "solved": "complete",
    "owned": "complete",
    "incompleted": "incompleted",
    "incomplete": "incompleted",
    "unsolved": "incompleted",
    "unowned": "incompleted",
}

CHALLENGE_SORT_ALIASES = {
    "name": "name",
    "release-date": "release_date",
    "release_date": "release_date",
    "release": "release_date",
    "solves": "solves",
    "difficulty": "user_difficulty",
    "user-difficulty": "user_difficulty",
    "user_difficulty": "user_difficulty",
}

SEARCH_TARGET_ALIASES = {
    "machine": "machines",
    "machines": "machines",
    "challenge": "challenges",
    "challenges": "challenges",
    "user": "users",
    "users": "users",
    "team": "teams",
    "teams": "teams",
}

SORT_TYPE_ALIASES = {
    "asc": "asc",
    "ascending": "asc",
    "desc": "desc",
    "descending": "desc",
}


def normalize_csv_choices(
    value: str | None,
    aliases: Mapping[str, str],
    field_name: str,
) -> list[str] | None:
    values = csv_values(value)
    if values is None:
        return None
    normalized: list[str] = []
    invalid: list[str] = []
    for item in values:
        alias = aliases.get(item.strip().lower())
        if alias is None:
            invalid.append(item)
        else:
            normalized.append(alias)
    if invalid:
        expected = ", ".join(sorted(set(aliases)))
        raise HTBError(f"{field_name} contains invalid values: {', '.join(invalid)}. Expected: {expected}.")
    return normalized


def normalize_optional_choice(
    value: str | None,
    aliases: Mapping[str, str],
    field_name: str,
) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = aliases.get(value.strip().lower())
    if normalized is None:
        expected = ", ".join(sorted(set(aliases)))
        raise HTBError(f"{field_name} must be one of: {expected}.")
    return normalized


class HTBClient:
    def __init__(
        self,
        config: HTBConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._config = config
        self._configured_version = detect_base_version(config.api_base_url)
        self._client = httpx.AsyncClient(
            base_url=config.api_base_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {config.api_token}",
                "User-Agent": "htb-mcp/0.1",
            },
            timeout=config.timeout,
            follow_redirects=True,
            transport=transport,
        )

    def _build_target(self, path: str, api_version: str | None) -> str:
        """Resolve a request path to the URL/relative-path httpx should call.

        Returns a relative path (merged with the client's base URL) for the
        configured default version, or an absolute URL when the request pins a
        different ``/api/vN`` version (e.g. machine flag submission on v5).
        """
        pinned_version, normalized = resolve_api_path(path)
        target_version = api_version or pinned_version
        if target_version and target_version != self._configured_version:
            base = base_url_for_version(self._config.api_base_url, target_version)
            return f"{base}{normalized}"
        return normalized

    async def __aenter__(self) -> "HTBClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: QueryParams = None,
        json_body: Any | None = None,
        api_version: str | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                self._build_target(path, api_version),
                params=self._normalize_params(params),
                json=json_body,
            )
        except httpx.HTTPError as exc:
            raise HTBError(f"Network error while calling HTB: {exc}") from exc
        return self._decode_response(response)

    async def bytes_request(self, path: str) -> tuple[bytes, str | None]:
        try:
            response = await self._client.get(self._build_target(path, None))
        except httpx.HTTPError as exc:
            raise HTBError(f"Network error while downloading from HTB: {exc}") from exc
        if response.status_code >= 400:
            self._raise_response_error(response)
        return response.content, response.headers.get("content-disposition")

    async def download_url(self, url: str) -> tuple[bytes, str | None]:
        try:
            async with httpx.AsyncClient(timeout=self._config.timeout, follow_redirects=True) as client:
                response = await client.get(url, headers={"User-Agent": "htb-mcp/0.1"})
        except httpx.HTTPError as exc:
            raise HTBError(f"Network error while downloading artifact: {exc}") from exc
        if response.status_code >= 400:
            self._raise_response_error(response)
        return response.content, response.headers.get("content-disposition")

    @staticmethod
    def _normalize_params(params: QueryParams) -> list[tuple[str, str]] | None:
        if not params:
            return None
        normalized: list[tuple[str, str]] = []
        for key, value in params.items():
            if value is None or value == "":
                continue
            if isinstance(value, list | tuple):
                for item in value:
                    normalized.append((key, str(item)))
            else:
                normalized.append((key, str(value)))
        return normalized

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        if response.status_code >= 400:
            HTBClient._raise_response_error(response)
        if response.status_code == 204 or not response.content:
            return {"status": True}
        content_type = response.headers.get("content-type", "")
        if "json" in content_type:
            return response.json()
        return {"status": True, "content": response.text}

    @staticmethod
    def _raise_response_error(response: httpx.Response) -> None:
        payload: Any | None
        message: str
        try:
            payload = response.json()
            if isinstance(payload, dict):
                message = str(payload.get("message") or payload.get("error") or payload)
            else:
                message = str(payload)
        except ValueError:
            payload = None
            message = response.text[:500] or response.reason_phrase
        raise HTBAPIError(response.status_code, message, payload)

    async def user_info(self) -> Any:
        return await self.request("GET", "/user/info")

    async def user_profile(self, user_id: int) -> Any:
        return await self.request("GET", f"/user/profile/basic/{user_id}")

    async def connection_status(self) -> Any:
        return await self.request("GET", "/connection/status")

    async def legacy_user_connection_status(self) -> Any:
        return await self.request("GET", "/user/connection/status")

    async def vpn_servers(self, product: str) -> Any:
        return await self.request("GET", "/connections/servers", params={"product": product})

    async def switch_vpn_server(self, vpn_id: int) -> Any:
        return await self.request("POST", f"/connections/servers/switch/{vpn_id}")

    async def search(self, query: str, target_type: str | None = None) -> Any:
        params: JsonMap = {"query": query}
        if target_type and target_type != "all":
            normalized_type = normalize_optional_choice(
                target_type,
                SEARCH_TARGET_ALIASES,
                "target_type",
            )
            params["tags"] = json.dumps([normalized_type])
        return await self.request("GET", "/search/fetch", params=params)

    async def list_machines(
        self,
        *,
        page: int,
        per_page: int,
        keyword: str | None,
        difficulty: str | None,
        state: str | None,
        status: str | None,
        sort_by: str | None,
        sort_type: str | None,
        todo: bool,
    ) -> Any:
        params: JsonMap = {"page": page, "per_page": per_page}
        add_if_present(params, "keyword", keyword)
        add_if_present(params, "state", csv_values(state))
        add_if_present(params, "difficulty[]", normalize_csv_choices(difficulty, DIFFICULTY_ALIASES, "difficulty"))
        add_if_present(params, "status", normalize_optional_choice(status, STATUS_ALIASES, "status"))
        add_if_present(params, "sort_by", sort_by)
        add_if_present(params, "sort_type", normalize_optional_choice(sort_type, SORT_TYPE_ALIASES, "sort_type"))
        if todo:
            params["todo"] = 1
        return await self.request("GET", "/machine/paginated", params=params)

    async def machine_profile(self, machine: str) -> Any:
        return await self.request("GET", f"/machine/profile/{machine}")

    async def active_machine(self) -> Any:
        return await self.request("GET", "/machine/active")

    async def recommended_machines(self) -> Any:
        return await self.request("GET", "/machine/recommended")

    async def machine_tasks(self, machine_id: int) -> Any:
        return await self.request("GET", f"/machines/{machine_id}/tasks")

    async def spawn_vm(self, machine_id: int) -> Any:
        return await self.request("POST", "/vm/spawn", json_body={"machine_id": machine_id})

    async def terminate_vm(self, machine_id: int) -> Any:
        return await self.request("POST", "/vm/terminate", json_body={"machine_id": machine_id})

    async def extend_vm(self, machine_id: int) -> Any:
        return await self.request("POST", "/vm/extend", json_body={"machine_id": machine_id})

    async def reset_vm(self, machine_id: int, mode: str) -> Any:
        path_by_mode = {
            "request": "/vm/reset",
            "vote": "/vm/reset/vote",
            "accept_vote": "/vm/reset/vote/accept",
        }
        try:
            path = path_by_mode[mode]
        except KeyError as exc:
            raise HTBError("mode must be one of: request, vote, accept_vote.") from exc
        return await self.request("POST", path, json_body={"machine_id": machine_id})

    async def submit_machine_flag(
        self,
        machine_id: int,
        flag: str,
        difficulty: int | None,
    ) -> Any:
        # HTB removed v4 /machine/own (returns 400 with code 2bc72d66) and moved
        # flag submission to /api/v5/machine/own. Payload shape is unchanged.
        # (Verified live 2026-06.)
        payload: JsonMap = {"id": machine_id, "flag": flag}
        add_if_present(payload, "difficulty", difficulty)
        return await self.request("POST", "/machine/own", json_body=payload, api_version="v5")

    async def list_challenges(
        self,
        *,
        page: int,
        per_page: int,
        keyword: str | None,
        difficulty: str | None,
        category: str | None,
        state: str | None,
        status: str | None,
        sort_by: str | None,
        sort_type: str | None,
        todo: bool,
    ) -> Any:
        params: JsonMap = {"page": page, "per_page": per_page}
        add_if_present(params, "keyword", keyword)
        add_if_present(params, "difficulty[]", normalize_csv_choices(difficulty, DIFFICULTY_ALIASES, "difficulty"))
        add_if_present(params, "category[]", int_csv_values(category))
        add_if_present(params, "state", csv_values(state))
        add_if_present(params, "status", normalize_optional_choice(status, STATUS_ALIASES, "status"))
        add_if_present(params, "sort_by", normalize_optional_choice(sort_by, CHALLENGE_SORT_ALIASES, "sort_by"))
        add_if_present(params, "sort_type", normalize_optional_choice(sort_type, SORT_TYPE_ALIASES, "sort_type"))
        if todo:
            params["todo"] = 1
        return await self.request("GET", "/challenges", params=params)

    async def challenge_info(self, challenge: str) -> Any:
        return await self.request("GET", f"/challenge/info/{challenge}")

    async def challenge_categories(self) -> Any:
        return await self.request("GET", "/challenge/categories/list")

    async def challenge_download_link(self, challenge_id: int) -> Any:
        return await self.request("GET", f"/challenges/{challenge_id}/download_link")

    async def start_challenge(self, challenge_id: int) -> Any:
        # HTB current API: challenge container spawn is POST /container/start {challenge_id}.
        # (The legacy /challenge/start route returns 404 — verified live 2026-06.)
        return await self.request("POST", "/container/start", json_body={"challenge_id": challenge_id})

    async def stop_challenge(self, challenge_id: int) -> Any:
        # HTB current API: POST /container/stop {challenge_id} (legacy /challenge/stop is 404).
        return await self.request("POST", "/container/stop", json_body={"challenge_id": challenge_id})

    async def start_container(self, container_id: int) -> Any:
        # The /container/start endpoint keys on challenge_id (not a separate container id).
        return await self.request("POST", "/container/start", json_body={"challenge_id": container_id})

    async def stop_container(self, container_id: int) -> Any:
        return await self.request("POST", "/container/stop", json_body={"challenge_id": container_id})

    async def submit_challenge_flag(self, challenge_id: int, flag: str) -> Any:
        return await self.request(
            "POST",
            "/challenge/own",
            json_body={"challenge_id": challenge_id, "flag": flag},
        )

    async def list_sherlocks(
        self,
        *,
        page: int,
        per_page: int,
        keyword: str | None,
        difficulty: str | None,
        category: str | None,
        state: str | None,
        status: str | None,
        sort_by: str | None,
        sort_type: str | None,
    ) -> Any:
        params: JsonMap = {"page": page, "per_page": per_page}
        add_if_present(params, "keyword", keyword)
        add_if_present(params, "difficulty[]", normalize_csv_choices(difficulty, DIFFICULTY_ALIASES, "difficulty"))
        add_if_present(params, "category[]", int_csv_values(category))
        add_if_present(params, "state", csv_values(state))
        add_if_present(params, "status", normalize_optional_choice(status, STATUS_ALIASES, "status"))
        add_if_present(params, "sort_by", sort_by)
        add_if_present(params, "sort_type", normalize_optional_choice(sort_type, SORT_TYPE_ALIASES, "sort_type"))
        return await self.request("GET", "/sherlocks", params=params)

    async def sherlock_info(self, sherlock: str) -> Any:
        if sherlock.isdecimal():
            return await self.request("GET", f"/sherlocks/{sherlock}/info")
        return await self.request("GET", f"/sherlocks/{sherlock}")

    async def sherlock_tasks(self, sherlock_id: int) -> Any:
        return await self.request("GET", f"/sherlocks/{sherlock_id}/tasks")

    async def sherlock_progress(self, sherlock_id: int) -> Any:
        return await self.request("GET", f"/sherlocks/{sherlock_id}/progress")

    async def sherlock_play(self, sherlock_id: int) -> Any:
        return await self.request("GET", f"/sherlocks/{sherlock_id}/play")

    async def sherlock_download_link(self, sherlock_id: int) -> Any:
        return await self.request("GET", f"/sherlocks/{sherlock_id}/download_link")

    async def submit_sherlock_task_flag(self, sherlock_id: int, task_id: int, flag: str) -> Any:
        return await self.request(
            "POST",
            f"/sherlocks/{sherlock_id}/tasks/{task_id}/flag",
            json_body={"flag": flag},
        )

    async def list_fortresses(self) -> Any:
        return await self.request("GET", "/fortresses")

    async def fortress_info(self, fortress_id: int) -> Any:
        return await self.request("GET", f"/fortress/{fortress_id}")

    async def fortress_flags(self, fortress_id: int) -> Any:
        return await self.request("GET", f"/fortress/{fortress_id}/flags")

    async def submit_fortress_flag(self, fortress_id: int, flag: str) -> Any:
        return await self.request("POST", f"/fortress/{fortress_id}/flag", json_body={"flag": flag})

    async def reset_fortress(self, fortress_id: int) -> Any:
        return await self.request("POST", f"/fortress/{fortress_id}/reset")

    async def list_seasons(self) -> Any:
        return await self.request("GET", "/season/list")

    async def active_season_machine(self) -> Any:
        return await self.request("GET", "/season/machine/active")

    async def season_machines(self, season_id: int) -> Any:
        return await self.request("GET", f"/season/machines/{season_id}")

    async def season_rewards(self, season_id: int) -> Any:
        return await self.request("GET", f"/season/rewards/{season_id}")

    async def season_user_rank(self, season_id: int) -> Any:
        return await self.request("GET", f"/season/user/rank/{season_id}")

    async def season_user_ranks(self, user_id: int) -> Any:
        return await self.request("GET", f"/season/user/{user_id}/ranks")

    async def season_leaderboard(self, leaderboard: str, season_id: int | None) -> Any:
        normalized = validate_choice(leaderboard, {"players", "teams"}, "leaderboard")
        params: JsonMap = {}
        add_if_present(params, "season", season_id)
        return await self.request("GET", f"/season/{normalized}/leaderboard", params=params)

    async def season_top_leaderboard(
        self,
        leaderboard: str,
        season_id: int,
        period: str,
    ) -> Any:
        normalized_leaderboard = validate_choice(leaderboard, {"players", "teams"}, "leaderboard")
        normalized_period = period.strip().upper()
        if normalized_period not in {"1Y", "6M", "3M", "1M", "1W"}:
            raise HTBError("period must be one of: 1Y, 6M, 3M, 1M, 1W.")
        return await self.request(
            "GET",
            f"/season/{normalized_leaderboard}/leaderboard/top/{season_id}",
            params={"period": normalized_period},
        )

    async def starting_point_progress(self) -> Any:
        return await self.request("GET", "/sp/tiers/progress")

    async def starting_point_tier(self, tier_id: int) -> Any:
        # HTB removed GET /sp/tier/{id} (400 with code 4c82c281) and, unlike
        # machine/own, ships no replacement route -- /sp/tiers/progress is the
        # only surviving Starting Point endpoint and lists tiers without their
        # machines. Return the matching tier's metadata from progress and point
        # callers at search/list tools for per-machine details. (Verified live 2026-06.)
        progress = await self.request("GET", "/sp/tiers/progress")
        tiers = progress.get("data", []) if isinstance(progress, dict) else []
        match = next(
            (tier for tier in tiers if isinstance(tier, dict) and tier.get("id") == tier_id),
            None,
        )
        if match is None:
            available = [tier.get("id") for tier in tiers if isinstance(tier, dict)]
            raise HTBError(f"Starting Point tier {tier_id} not found. Available tier ids: {available}.")
        return {
            "tier": match,
            "note": (
                "HTB removed the per-tier machine listing endpoint (GET /sp/tier/{id}). "
                "Only tier metadata is available now; use htb_search or htb_list_machines + "
                "htb_machine_info for Starting Point machine details."
            ),
        }

    async def submit_machine_task_flag(self, machine_id: int, task_id: int, flag: str) -> Any:
        return await self.request(
            "POST",
            f"/machines/{machine_id}/tasks/{task_id}/flag",
            json_body={"flag": flag},
        )

    async def list_prolabs(self) -> Any:
        return await self.request("GET", "/prolabs")

    async def prolab_overview(self, prolab_id: int) -> Any:
        return await self.request("GET", f"/prolab/{prolab_id}/overview")

    async def prolab_machines(self, prolab_id: int) -> Any:
        return await self.request("GET", f"/prolab/{prolab_id}/machines")

    async def prolab_flags(self, prolab_id: int) -> Any:
        return await self.request("GET", f"/prolab/{prolab_id}/flags")

    async def submit_prolab_flag(self, prolab_id: int, flag: str) -> Any:
        return await self.request("POST", f"/prolab/{prolab_id}/flag", json_body={"flag": flag})

    async def raw_get(self, path: str, params_json: str) -> Any:
        return await self.request("GET", path, params=parse_params_json(params_json))

    async def raw_post(self, path: str, body_json: str) -> Any:
        return await self.request("POST", path, json_body=parse_params_json(body_json))
