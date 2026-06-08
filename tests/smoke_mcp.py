from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "htb_mcp.server"],
        cwd=str(project_root),
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            result = await session.call_tool("htb_whoami", {})
    print(
        {
            "tool_count": len(tools.tools),
            "has_whoami": any(tool.name == "htb_whoami" for tool in tools.tools),
            "whoami_blocks": len(result.content),
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
