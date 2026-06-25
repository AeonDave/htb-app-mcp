"""Offline regression tests for HTB API path/version routing.

No network or API token required: requests are captured with httpx.MockTransport.

Run standalone:  python tests/test_client_routing.py
Run with pytest: pytest tests/test_client_routing.py
"""

from __future__ import annotations

import json

import anyio
import httpx

from htb_mcp.client import (
    HTBClient,
    base_url_for_version,
    detect_base_version,
    resolve_api_path,
)
from htb_mcp.config import HTBConfig
from htb_mcp.errors import HTBError

_V4 = "https://labs.hackthebox.com/api/v4"
_V5 = "https://labs.hackthebox.com/api/v5"


def _capturing_client(responder=None) -> tuple[HTBClient, list[dict]]:
    captured: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode() if request.content else ""
        captured.append(
            {
                "method": request.method,
                "url": str(request.url),
                "json": json.loads(body) if body else None,
            }
        )
        if responder is not None:
            return responder(request)
        return httpx.Response(200, json={"status": True})

    client = HTBClient(HTBConfig(api_token="test-token"), transport=httpx.MockTransport(handler))
    return client, captured


# --- pure helpers ---------------------------------------------------------


def test_resolve_api_path_defaults_to_no_version() -> None:
    assert resolve_api_path("/machine/own") == (None, "/machine/own")
    assert resolve_api_path("machine/own") == (None, "/machine/own")


def test_resolve_api_path_pins_explicit_version() -> None:
    assert resolve_api_path("/api/v5/machine/own") == ("v5", "/machine/own")
    assert resolve_api_path("/api/v4/machine/active") == ("v4", "/machine/active")
    assert resolve_api_path(f"{_V5}/machine/own") == ("v5", "/machine/own")


def test_resolve_api_path_rejects_traversal_and_foreign_hosts() -> None:
    for bad in ("/api/v5/../secret", "https://evil.example.com/api/v5/x"):
        try:
            resolve_api_path(bad)
        except HTBError:
            continue
        raise AssertionError(f"expected HTBError for {bad!r}")


def test_version_base_helpers() -> None:
    assert detect_base_version(_V4) == "v4"
    assert detect_base_version("https://labs.hackthebox.com") is None
    assert base_url_for_version(_V4, "v5") == _V5
    # No version segment in base -> append one.
    assert base_url_for_version("https://labs.hackthebox.com", "v5") == _V5


# --- client routing -------------------------------------------------------


async def _submit_flag(difficulty: int | None) -> dict:
    client, captured = _capturing_client()
    async with client:
        await client.submit_machine_flag(912, "deadbeef", difficulty)
    return captured[0]


def test_submit_machine_flag_targets_v5() -> None:
    call = anyio.run(_submit_flag, None)
    assert call["method"] == "POST"
    assert call["url"] == f"{_V5}/machine/own"
    assert call["json"] == {"id": 912, "flag": "deadbeef"}


def test_submit_machine_flag_includes_difficulty() -> None:
    call = anyio.run(_submit_flag, 50)
    assert call["json"] == {"id": 912, "flag": "deadbeef", "difficulty": 50}


async def _spawn() -> dict:
    client, captured = _capturing_client()
    async with client:
        await client.spawn_vm(1)
    return captured[0]


def test_v4_endpoints_unchanged() -> None:
    call = anyio.run(_spawn)
    assert call["url"] == f"{_V4}/vm/spawn"
    assert call["json"] == {"machine_id": 1}


async def _raw_post(path: str) -> dict:
    client, captured = _capturing_client()
    async with client:
        await client.raw_post(path, json.dumps({"id": 1, "flag": "x"}))
    return captured[0]


def test_raw_post_can_pin_version() -> None:
    call = anyio.run(_raw_post, "/api/v5/machine/own")
    assert call["url"] == f"{_V5}/machine/own"


def test_raw_post_defaults_to_v4() -> None:
    call = anyio.run(_raw_post, "/machine/own")
    assert call["url"] == f"{_V4}/machine/own"


_TIERS = {
    "data": [
        {"id": 1, "name": "Tier 0", "description": "foundation", "completion_percentage": 55},
        {"id": 2, "name": "Tier 1", "description": "walk", "completion_percentage": 54},
    ]
}


async def _starting_point_tier(tier_id: int) -> tuple[Any, list[dict]]:
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_TIERS)

    client, captured = _capturing_client(responder)
    async with client:
        result = await client.starting_point_tier(tier_id)
    return result, captured


def test_starting_point_tier_uses_progress_not_removed_route() -> None:
    result, captured = anyio.run(_starting_point_tier, 2)
    # Must hit the surviving progress route, never the removed /sp/tier/{id}.
    assert captured[0]["url"] == f"{_V4}/sp/tiers/progress"
    assert all("/sp/tier/" not in c["url"] for c in captured)
    assert result["tier"]["id"] == 2
    assert "note" in result


def test_starting_point_tier_unknown_id_raises() -> None:
    async def _run() -> None:
        try:
            await _starting_point_tier(99)
        except HTBError:
            return
        raise AssertionError("expected HTBError for unknown tier id")

    anyio.run(_run)


def _run_all() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    failures = 0
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - surface every failure
            failures += 1
            print(f"FAIL {test.__name__}: {exc!r}")
        else:
            print(f"ok   {test.__name__}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
