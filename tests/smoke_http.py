from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


def _read_token(project_root: Path) -> str:
    value = dotenv_values(project_root / ".env").get("API_TOKEN", "")
    if not value:
        raise RuntimeError("API_TOKEN missing in .env for smoke test")
    return value


async def _call_server(token: str) -> None:
    async with streamablehttp_client(
        "http://127.0.0.1:8765/mcp",
        headers={"Authorization": f"Bearer {token}"},
    ) as (read, write, get_session_id):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("htb_whoami", {})
            print(
                {
                    "blocks": len(result.content),
                    "is_error": bool(result.isError),
                    "session_id": get_session_id(),
                }
            )


async def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    token = _read_token(project_root)
    env = os.environ.copy()
    env["HTB_LOAD_DOTENV"] = "0"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "htb_mcp.server",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
            "--port",
            "8765",
            "--log-level",
            "ERROR",
        ],
        cwd=project_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        await asyncio.sleep(2)
        await _call_server(token)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)


if __name__ == "__main__":
    asyncio.run(main())
