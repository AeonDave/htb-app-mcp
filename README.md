# HTB App MCP

MCP locale per usare i servizi di **Hack The Box app** (`app.hackthebox.com`) tramite API v4 su:

```text
https://labs.hackthebox.com/api/v4
```

Questo progetto **non** usa `pyhackthebox`: il client parla direttamente con HTB via `httpx` e passa il token come:

```http
Authorization: Bearer <HTB_APP_TOKEN>
```

Non confonderlo con il MCP CTF ufficiale su `mcp.hackthebox.ai/v1/ctf/mcp/`: questo server è per Labs/App HTB, quindi Machines, Challenges, Sherlocks, Fortresses, Starting Point e Seasonal.

## Stato attuale

- Transport consigliato: **HTTP locale Streamable MCP** su `http://127.0.0.1:8000/mcp`.
- HTTP è **stateless di default**: se riavvii `htb-app-mcp`, il client non resta bloccato con `Session not found`.
- Token consigliato: header MCP `Authorization: Bearer <HTB_APP_TOKEN>`, senza `.env`.
- Fallback supportato: stdio + `.env`/variabili ambiente.
- Tool esposti: **49**.

## Setup

Prerequisiti:

- Python 3.11+
- `uv`
- HTB App Token creato da `app.hackthebox.com`

Installa le dipendenze:

```bash
uv sync
```

## Modalità consigliata: HTTP con header Authorization

Avvia il server:

```bash
uv run htb-app-mcp --transport http --host 127.0.0.1 --port 8000
```

Configura il client MCP così:

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

In questa modalità il token arriva dal client MCP e viene inoltrato solo verso HTB. Non serve `.env`.

### Restart del server

HTTP parte stateless di default. Questo evita il problema:

```text
Session not found
```

Quindi puoi riavviare:

```bash
uv run htb-app-mcp --transport http --host 127.0.0.1 --port 8000
```

e il client MCP può riconnettersi senza aprire una nuova chat. Se il client continua a usare una connessione vecchia, ricarica i server MCP lato client.

Per debug protocollo puoi forzare la modalità stateful:

```bash
uv run htb-app-mcp --transport http --stateful-http
```

## Modalità alternativa: stdio

Stdio è utile se un host MCP vuole lanciare direttamente il processo locale.

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

Puoi anche usare `.env` come fallback locale:

```bash
cp .env.example .env
# modifica .env e imposta HTB_API_TOKEN
uv run htb-app-mcp
```

`.env` è ignorato da git.

## Tool principali

| Area | Tool |
|---|---|
| Account | `htb_whoami`, `htb_user_profile` |
| VPN | `htb_connection_status`, `htb_vpn_servers`, `htb_switch_vpn_server`, `htb_download_ovpn` |
| Search | `htb_search`, `htb_api_get` |
| Machines | `htb_list_machines`, `htb_machine_info`, `htb_active_machine`, `htb_recommended_machines`, `htb_machine_tasks` |
| Machine actions | `htb_spawn_machine`, `htb_stop_machine`, `htb_extend_machine`, `htb_reset_machine`, `htb_submit_machine_flag` |
| Challenges | `htb_list_challenges`, `htb_challenge_info`, `htb_challenge_categories`, `htb_download_challenge` |
| Challenge actions | `htb_start_challenge`, `htb_stop_challenge`, `htb_start_container`, `htb_stop_container`, `htb_submit_challenge_flag` |
| Sherlocks | `htb_list_sherlocks`, `htb_sherlock_info`, `htb_sherlock_tasks`, `htb_sherlock_progress`, `htb_sherlock_play`, `htb_download_sherlock`, `htb_submit_sherlock_task_flag` |
| Fortresses | `htb_list_fortresses`, `htb_fortress_info`, `htb_fortress_flags`, `htb_submit_fortress_flag`, `htb_reset_fortress` |
| Seasonal | `htb_list_seasons`, `htb_active_season_machine`, `htb_season_machines`, `htb_season_rewards`, `htb_season_user_rank`, `htb_season_user_ranks`, `htb_season_leaderboard`, `htb_season_top_leaderboard` |
| Starting Point | `htb_starting_point_progress`, `htb_starting_point_tier` |

Resource:

```text
htb://service-map
```

Prompt:

```text
htb_target_workflow
```

## Endpoint HTB coperti

Il server usa endpoint reali verificati su `labs.hackthebox.com/api/v4`, tra cui:

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
```

Alcuni endpoint documentati online sono vecchi e oggi rispondono 404, per esempio `/machine/list`, `/machines`, `/starting-point/machines`.

## Download

Download supportati:

- OVPN: `htb_download_ovpn`
- Challenge ZIP: `htb_download_challenge`
- Sherlock ZIP: `htb_download_sherlock`

Default:

- directory: `downloads`
- password ZIP: `hackthebox`
- estrazione ZIP: attiva per challenge/Sherlock
- download ZIP serializzati con intervallo minimo per ridurre `429 Too Many Requests`

Puoi cambiare la directory:

```bash
export HTB_DOWNLOAD_DIR="D:/Sources/htb-app-mcp/downloads"
```

## Variabili ambiente

| Variabile | Default | Uso |
|---|---:|---|
| `HTB_API_TOKEN` | vuoto | Token HTB per stdio o fallback HTTP |
| `API_TOKEN` | vuoto | Alias supportato per compatibilità |
| `HTB_TOKEN` | vuoto | Alias supportato |
| `HTB_API_BASE_URL` | `https://labs.hackthebox.com/api/v4` | Override base API |
| `HTB_DOWNLOAD_DIR` | `downloads` | Directory download |
| `HTB_TIMEOUT` | `30` | Timeout HTTP verso HTB |
| `HTB_LOAD_DOTENV` | `1` | Imposta `0` per disabilitare `.env` |
| `HTB_MCP_TRANSPORT` | `stdio` | `stdio`, `http`, `streamable-http` |
| `HTB_MCP_HOST` | `127.0.0.1` | Bind address HTTP |
| `HTB_MCP_PORT` | `8000` | Porta HTTP |
| `HTB_MCP_PATH` | `/mcp` | Path MCP HTTP |
| `HTB_MCP_STATELESS_HTTP` | `1` in HTTP | HTTP stateless di default |
| `HTB_MCP_JSON_RESPONSE` | `0` | Risposte JSON dove supportate |
| `HTB_MCP_LOG_LEVEL` | `INFO` | Log server |
| `HTB_MCP_VERBOSE_HTTP` | `0` | Se `1`, riabilita log HTTPX dettagliati |
| `HTB_DOWNLOAD_MIN_INTERVAL` | `1.0` | Secondi minimi tra download ZIP |

## CLI

```bash
uv run htb-app-mcp --help
```

Opzioni principali:

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

## Validazione locale

Smoke test client diretto:

```bash
uv run python tests/smoke_client.py
```

Smoke test MCP stdio:

```bash
uv run python tests/smoke_mcp.py
```

Smoke test MCP HTTP con header Authorization:

```bash
uv run python tests/smoke_http.py
```

## Troubleshooting

### `Session not found`

Aggiorna il codice e riavvia in HTTP default/stateless:

```bash
uv run htb-app-mcp --transport http --host 127.0.0.1 --port 8000
```

Se il client ha ancora una connessione vecchia, usa reload MCP servers lato client.

### `404 Not Found` su `/mcp`

Controlla che:

- il server sia avviato con `--transport http`
- la config MCP punti a `http://127.0.0.1:8000/mcp`
- `HTB_MCP_PATH` o `--path` non siano diversi da `/mcp`

### `ConnectionResetError [WinError 10054]` su Windows

Il transport HTTP forza il selector event loop di Windows per evitare stack trace rumorosi quando un client MCP chiude una connessione HTTP/SSE già completata.

### Traceback o `ASGI callable returned without completing response` su Ctrl+C

La gestione shutdown è cross-platform: su Linux/macOS usa il signal handling standard di Uvicorn, mentre su Windows abilita solo il selector event loop per evitare rumore specifico del Proactor. In tutti i casi il server filtra il rumore benigno generato da Uvicorn/Starlette quando chiudi con Ctrl+C mentre ci sono stream MCP HTTP aperti. Se hai bisogno dei log completi per debug, imposta `HTB_MCP_VERBOSE_HTTP=1`.

### `422 Unprocessable Entity`

HTB rifiuta parametri non validi. Il server normalizza i casi più comuni:

- `Easy` -> `easy`
- `Very Easy` -> `very-easy`
- `unsolved` -> `incompleted`
- `solved` -> `complete`
- `sort_by=difficulty` -> `user_difficulty` per challenges
- `target_type=challenge` -> `challenges` per search

Se HTB cambia schema, usa `htb_api_get` per testare un endpoint read-only.

### `403 Forbidden` durante download

Non è necessariamente un bug: HTB può negare l'accesso a challenge/file non disponibili per il tuo account, piano, stato o permessi.

### `429 Too Many Requests`

Hai colpito rate limit HTB. Il server serializza i download ZIP, ma se un agente chiede molti download ravvicinati conviene aspettare qualche minuto o aumentare:

```bash
export HTB_DOWNLOAD_MIN_INTERVAL=2.0
```

### Log con URL firmati

I log HTTPX/httpcore sono silenziati di default per evitare di stampare URL temporanei S3. Per debug:

```bash
export HTB_MCP_VERBOSE_HTTP=1
```

Non condividere log verbose: possono contenere URL presigned temporanei.

## Sicurezza

- Tieni il server HTTP su loopback (`127.0.0.1`).
- Non committare `.env` o token.
- Non incollare token nei log o nel README.
- Evita `HTB_MCP_VERBOSE_HTTP=1` salvo debug locale.
- Le azioni `spawn`, `stop`, `reset`, `submit flag`, `switch VPN` hanno side effect sul tuo account HTB.

## Note API

Le API HTB App v4 non sono ufficialmente stabili per integrazioni esterne. Molti riferimenti pubblici sono community-maintained o reverse-engineered; HTB può cambiare path, payload o permessi senza preavviso.
