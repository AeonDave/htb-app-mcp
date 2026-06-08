from __future__ import annotations

import asyncio

from htb_mcp.client import HTBClient
from htb_mcp.config import load_config


async def main() -> None:
    config = load_config()
    async with HTBClient(config) as client:
        user = await client.user_info()
        connection = await client.legacy_user_connection_status()
        challenges = await client.list_challenges(
            page=1,
            per_page=5,
            keyword=None,
            difficulty=None,
            category=None,
            state=None,
            status=None,
            sort_by=None,
            sort_type=None,
            todo=False,
        )
        seasons = await client.list_seasons()
        active_season_machine = await client.active_season_machine()
    print(
        {
            "user_id": user.get("info", {}).get("id"),
            "connection_status": connection.get("status"),
            "challenge_count": len(challenges.get("data", [])),
            "season_count": len(seasons.get("data", [])),
            "active_season_machine": active_season_machine.get("data", {}).get("name"),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
