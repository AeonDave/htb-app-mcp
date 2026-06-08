# HTB App MCP

Local MCP server for **Hack The Box App** services via the HTB API v4 at:

```text
https://labs.hackthebox.com/api/v4
```

This project does **not** use `pyhackthebox`: the client talks directly to HTB via `httpx` and authenticates with:

```http
Authorization: Bearer <HTB_APP_TOKEN>
```

Do not confuse this with the official HTB CTF MCP at `mcp.hackthebox.ai/v1/ctf/mcp/`. This server is for HTB App/Labs content: Machines, Challenges, Sherlocks, Fortresses, Starting Point, Seasonal, and Pro Labs.

## Current status

- Recommended transport: **local Streamable HTTP MCP** on `http://127.0.0.1:8000/mcp`.
- HTTP is **stateless by default**: restart the server without your MCP client getting stuck on `Session not found`.
- Recommended auth: MCP header `Authorization: Bearer <HTB_APP_TOKEN>`, no `.env` needed.
- Fallback: stdio + `.env` / environment variables.
- Exposed tools: **56**.

## Setup

Prerequisites:

- Python 3.11+
- `uv`
- HTB App Token from `app.hackthebox.com`

Install dependencies:

```bash
uv sync
```

## Recommended mode: HTTP with Authorization header

Start the server:

```bash
uv run htb-app-mcp --transport http --host 127.0.0.1 --port 8000
```

Configure your MCP client:

```json
{
  "mcpServers": {
    "htb-app-mcp": {
      "url": "http://127.0.0.1:8000/mcp",
      "type": "http",
      "headers": {
        "Authorization": "Bearer <HTB_APP_TOKEN>"
      }
    }
  }
}
```

In this mode the token comes from the MCP client and is forwarded to HTB only. No `.env` required.

### Restarting the server

HTTP is stateless by default, avoiding the `Session not found` issue. You can restart:

```bash
uv run htb-app-mcp --transport http --host 127.0.0.1 --port 8000
```

and the MCP client can reconnect without starting a new chat. If the client still uses an old connection, reload the MCP servers on the client side.

For protocol debugging you can force stateful mode:

```bash
uv run htb-app-mcp --transport http --stateful-http
```

## Alternative mode: stdio

Stdio is useful when an MCP host wants to launch the local process directly.

Config:

```json
{
  "mcpServers": {
    "htb-app-mcp": {
      "command": "uv",
      "args": ["--directory", "D:\\Sources\\htb-app-mcp", "run", "htb-app-mcp"],
      "env": {
        "HTB_API_TOKEN": "<HTB_APP_TOKEN>"
      }
    }
  }
}
```

You can also use `.env` as a local fallback:

```bash
cp .env.example .env
# edit .env and set HTB_API_TOKEN (or API_TOKEN)
uv run htb-app-mcp
```

`.env` is gitignored.

## Tools

| Area | Tools |
|---|---|
| Account | `htb_whoami`, `htb_user_profile` |
| VPN | `htb_connection_status`, `htb_vpn_servers`, `htb_switch_vpn_server`, `htb_download_ovpn` |
| Search | `htb_search`, `htb_api_get`, `htb_api_post` |
| Machines | `htb_list_machines`, `htb_machine_info`, `htb_active_machine`, `htb_recommended_machines`, `htb_machine_tasks` |
| Machine actions | `htb_spawn_machine`, `htb_stop_machine`, `htb_extend_machine`, `htb_reset_machine`, `htb_submit_machine_flag` |
| Challenges | `htb_list_challenges`, `htb_challenge_info`, `htb_challenge_categories`, `htb_download_challenge` |
| Challenge actions | `htb_start_challenge`, `htb_stop_challenge`, `htb_start_container`, `htb_stop_container`, `htb_submit_challenge_flag` |
| Sherlocks | `htb_list_sherlocks`, `htb_sherlock_info`, `htb_sherlock_tasks`, `htb_sherlock_progress`, `htb_sherlock_play`, `htb_download_sherlock`, `htb_submit_sherlock_task_flag` |
| Fortresses | `htb_list_fortresses`, `htb_fortress_info`, `htb_fortress_flags`, `htb_submit_fortress_flag`, `htb_reset_fortress` |
| Seasonal | `htb_list_seasons`, `htb_active_season_machine`, `htb_season_machines`, `htb_season_rewards`, `htb_season_user_rank`, `htb_season_user_ranks`, `htb_season_leaderboard`, `htb_season_top_leaderboard` |
| Starting Point | `htb_starting_point_progress`, `htb_starting_point_tier`, `htb_submit_machine_task` |
| Pro Labs | `htb_list_prolabs`, `htb_prolab_overview`, `htb_prolab_machines`, `htb_prolab_flags`, `htb_submit_prolab_flag` |

Resource:

```text
htb://service-map
```

Prompt:

```text
htb_target_workflow
```

## HTB endpoints covered

The server uses verified real endpoints on `labs.hackthebox.com/api/v4`, including:

```text
GET  /user/info
GET  /connection/status
GET  /user/connection/status
GET  /connections/servers?product=...
POST /connections/servers/switch/{vpnId}
GET  /access/ovpnfile/{vpnId}/0
GET  /access/ovpnfile/{vpnId}/0/1

GET  /search/fetch

GET  /machine/paginated
GET  /machine/profile/{machineSlug}
GET  /machine/active
GET  /machine/recommended
GET  /machines/{machineId}/tasks
POST /vm/spawn
POST /vm/terminate
POST /vm/extend
POST /vm/reset
POST /vm/reset/vote
POST /vm/reset/vote/accept
POST /machine/own

GET  /challenges
GET  /challenge/info/{challengeSlug}
GET  /challenge/categories/list
GET  /challenges/{challengeId}/download_link
POST /challenge/start
POST /challenge/stop
POST /container/start
POST /container/stop
POST /challenge/own

GET  /sherlocks
GET  /sherlocks/{sherlockId}/info
GET  /sherlocks/{sherlockId}/tasks
GET  /sherlocks/{sherlockId}/progress
GET  /sherlocks/{sherlockId}/play
GET  /sherlocks/{sherlockId}/download_link
POST /sherlocks/{sherlockId}/tasks/{taskId}/flag

GET  /fortresses
GET  /fortress/{fortressId}
GET  /fortress/{fortressId}/flags
POST /fortress/{fortressId}/flag
POST /fortress/{fortressId}/reset

GET  /season/list
GET  /season/machine/active
GET  /season/machines/{seasonId}
GET  /season/rewards/{seasonId}
GET  /season/user/rank/{seasonId}
GET  /season/user/{userId}/ranks
GET  /season/{players|teams}/leaderboard
GET  /season/{players|teams}/leaderboard/top/{seasonId}

GET  /sp/tiers/progress
GET  /sp/tier/{tierId}

GET  /prolabs
GET  /prolab/{prolabId}/overview
GET  /prolab/{prolabId}/machines
GET  /prolab/{prolabId}/flags
POST /prolab/{prolabId}/flag
```

Some older endpoints documented online now return 404 (e.g. `/machine/list`, `/machines`, `/starting-point/machines`).

## Downloads

Supported downloads:

- OVPN: `htb_download_ovpn`
- Challenge ZIP: `htb_download_challenge`
- Sherlock ZIP: `htb_download_sherlock`

Defaults:

- directory: `downloads`
- ZIP password: `hackthebox`
- ZIP extraction: enabled for challenges and Sherlocks
- ZIP downloads serialized with a minimum interval to reduce `429 Too Many Requests`

Change the directory:

```bash
export HTB_DOWNLOAD_DIR="D:/Sources/htb-app-mcp/downloads"
```

## Environment variables

| Variable | Default | Usage |
|---|---|---:|---|
| `HTB_API_TOKEN` | empty | HTB token for stdio or HTTP fallback |
| `API_TOKEN` | empty | Supported alias for compatibility |
| `HTB_TOKEN` | empty | Supported alias |
| `HTB_API_BASE_URL` | `https://labs.hackthebox.com/api/v4` | Override base API URL |
| `HTB_DOWNLOAD_DIR` | `downloads` | Download directory |
| `HTB_TIMEOUT` | `30` | HTTP timeout to HTB in seconds |
| `HTB_LOAD_DOTENV` | `1` | Set to `0` to disable `.env` loading |
| `HTB_MCP_TRANSPORT` | `stdio` | `stdio`, `http`, `streamable-http` |
| `HTB_MCP_HOST` | `127.0.0.1` | HTTP bind address |
| `HTB_MCP_PORT` | `8000` | HTTP port |
| `HTB_MCP_PATH` | `/mcp` | MCP HTTP path |
| `HTB_MCP_STATELESS_HTTP` | `1` in HTTP mode | HTTP stateless by default |
| `HTB_MCP_JSON_RESPONSE` | `0` | Return JSON responses where supported |
| `HTB_MCP_LOG_LEVEL` | `INFO` | Server log level |
| `HTB_MCP_VERBOSE_HTTP` | `0` | Set to `1` to re-enable verbose HTTPX logging |
| `HTB_DOWNLOAD_MIN_INTERVAL` | `1.0` | Minimum seconds between ZIP downloads |
| `HTB_MCP_GRACEFUL_SHUTDOWN_TIMEOUT` | `5` | Graceful shutdown timeout in seconds |
| `HTB_MCP_WINDOWS_SELECTOR_EVENT_LOOP` | `1` | Use selector event loop on Windows |

## CLI

```bash
uv run htb-app-mcp --help
```

Main options:

```text
--transport {stdio,http,streamable-http}
--host 127.0.0.1
--port 8000
--path /mcp
--stateless-http
--stateful-http
--json-response
--log-level INFO
--graceful-shutdown-timeout 5
```

## Local validation

Smoke test with direct client:

```bash
uv run python tests/smoke_client.py
```

Smoke test with MCP stdio:

```bash
uv run python tests/smoke_mcp.py
```

Smoke test with MCP HTTP and Authorization header:

```bash
uv run python tests/smoke_http.py
```

## Troubleshooting

### `Session not found`

Update the code and restart in default HTTP stateless mode:

```bash
uv run htb-app-mcp --transport http --host 127.0.0.1 --port 8000
```

If the client still holds an old connection, use reload MCP servers on the client side.

### `404 Not Found` on `/mcp`

Check that:

- the server is started with `--transport http`
- the MCP config points to `http://127.0.0.1:8000/mcp`
- `HTB_MCP_PATH` or `--path` is not set to something other than `/mcp`

### `ConnectionResetError [WinError 10054]` on Windows

The HTTP transport forces the selector event loop on Windows to avoid noisy stack traces when an MCP client closes a completed HTTP/SSE connection.

### Traceback or `ASGI callable returned without completing response` on Ctrl+C

Shutdown handling is cross-platform: on Linux/macOS it uses standard Uvicorn signal handling; on Windows it enables the selector event loop only to avoid Proactor-specific noise. In all cases the server filters benign noise from Uvicorn/Starlette when closing HTTP MCP streams with Ctrl+C. For full debug logs, set `HTB_MCP_VERBOSE_HTTP=1`.

### `422 Unprocessable Entity`

HTB rejects invalid parameters. The server normalizes common cases:

- `Easy` -> `easy`
- `Very Easy` -> `very-easy`
- `unsolved` -> `incompleted`
- `solved` -> `complete`
- `sort_by=difficulty` -> `user_difficulty` for challenges
- `target_type=challenge` -> `challenges` for search

If HTB changes the schema, use `htb_api_get` to test a read-only endpoint.

### `403 Forbidden` during download

This is not necessarily a bug: HTB may deny access to challenges or files not available for your account plan, tier, status, or permissions.

### `429 Too Many Requests`

You hit the HTB rate limit. The server serializes ZIP downloads, but if an agent requests many consecutive downloads, wait a few minutes or increase:

```bash
export HTB_DOWNLOAD_MIN_INTERVAL=2.0
```

### Logs with signed URLs

HTTPX and httpcore logs are silenced by default to avoid printing temporary S3 URLs. For debugging:

```bash
export HTB_MCP_VERBOSE_HTTP=1
```

Do not share verbose logs: they may contain temporary presigned URLs.

## Security

- Keep the HTTP server on loopback (`127.0.0.1`).
- Do not commit `.env` or tokens.
- Do not paste tokens in logs or the README.
- Avoid `HTB_MCP_VERBOSE_HTTP=1` outside local debugging.
- Tools like `spawn`, `stop`, `reset`, `submit flag`, `switch VPN` have side effects on your HTB account.

## API notes

HTB App v4 APIs are not officially stable for external integrations. Most public references are community-maintained or reverse-engineered; HTB may change paths, payloads, or permissions without notice.
