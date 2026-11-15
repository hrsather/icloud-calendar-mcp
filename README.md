# icloud-calendar-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant read, add, change and
delete events in your iCloud (Apple) Calendar. It talks to iCloud over CalDAV, so it runs anywhere
(Linux, containers, macOS) without EventKit or AppleScript.

- Tools: `list_calendars`, `list_events`, `get_event`, `create_event`, `update_event`, `delete_event`
- Transports: stdio (default) and SSE with a required bearer token
- Optional read-only mode
- Configuration through environment variables only; secrets are never logged

## Create an app-specific password

The server signs in with your Apple ID and an app-specific password, never your Apple ID password.

1. Sign in at [account.apple.com](https://account.apple.com).
2. Open **Sign-In and Security** → **App-Specific Passwords**.
3. Create one named e.g. `calendar-mcp` and copy it.

Revoke it from the same page at any time.

## Install

### Docker

```sh
docker run --rm -i \
  -e ICLOUD_APPLE_ID=user@example.com \
  -e ICLOUD_APP_PASSWORD=abcd-efgh-ijkl-mnop \
  ghcr.io/hrsather/icloud-calendar-mcp:latest
```

Images are published for `linux/amd64` and `linux/arm64`, tagged `X.Y.Z`, `X.Y` and `latest`. Pin
an exact version in production.

### From source

```sh
uvx --from git+https://github.com/hrsather/icloud-calendar-mcp icloud-calendar-mcp
```

or

```sh
git clone https://github.com/hrsather/icloud-calendar-mcp
cd icloud-calendar-mcp
uv sync
uv run icloud-calendar-mcp
```

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `ICLOUD_APPLE_ID` | yes | Apple ID email |
| `ICLOUD_APP_PASSWORD` | yes | App-specific password |
| `MCP_BEARER_TOKEN` | sse only | Token clients must send as `Authorization: Bearer <token>` |
| `ICLOUD_MCP_READ_ONLY` | no | `true` hides `create_event`, `update_event` and `delete_event` |
| `ICLOUD_MCP_TIMEZONE` / `TZ` | no | IANA timezone applied to times without an offset (default `UTC`), e.g. `Europe/London` |

Each of `ICLOUD_APPLE_ID`, `ICLOUD_APP_PASSWORD` and `MCP_BEARER_TOKEN` also accepts a `_FILE`
variant (for example `ICLOUD_APP_PASSWORD_FILE=/run/secrets/app_password`) for container secrets.

Command line: `--transport stdio|sse` (default `stdio`), `--host` (default `127.0.0.1`), `--port`
(default `8080`), `--version`.

## Client configuration

### Claude Desktop

```json
{
  "mcpServers": {
    "icloud-calendar": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/hrsather/icloud-calendar-mcp", "icloud-calendar-mcp"],
      "env": {
        "ICLOUD_APPLE_ID": "user@example.com",
        "ICLOUD_APP_PASSWORD": "abcd-efgh-ijkl-mnop"
      }
    }
  }
}
```

### Claude Code

```sh
claude mcp add icloud-calendar \
  -e ICLOUD_APPLE_ID=user@example.com \
  -e ICLOUD_APP_PASSWORD=abcd-efgh-ijkl-mnop \
  -- uvx --from git+https://github.com/hrsather/icloud-calendar-mcp icloud-calendar-mcp
```

### Any MCP client over SSE

Run the server where the client can reach it:

```sh
docker run -p 8080:8080 \
  -e ICLOUD_APPLE_ID=user@example.com \
  -e ICLOUD_APP_PASSWORD=abcd-efgh-ijkl-mnop \
  -e MCP_BEARER_TOKEN="$(openssl rand -hex 32)" \
  ghcr.io/hrsather/icloud-calendar-mcp:latest --transport sse --host 0.0.0.0
```

Point the client at `http://<host>:8080/sse` with the header `Authorization: Bearer <token>`.
The server speaks plain HTTP; put it behind TLS or keep it on a private network.

## Tools

| Tool | Description |
| --- | --- |
| `list_calendars` | Calendars that can hold events, with `id` and `name` |
| `list_events(start, end, calendar?)` | Events in a range. `start`/`end` are ISO 8601; omit `calendar` (name or id) to search all. Recurring events are expanded into occurrences |
| `get_event(uid, calendar?)` | One event by UID. For a recurring event, the series and its `rrule` |
| `create_event(calendar, summary, start, end?, location?, description?, rrule?)` | Create an event. A date-only `start` creates an all-day event; `end` defaults to +1 hour (or +1 day); `rrule` is e.g. `FREQ=WEEKLY;COUNT=4` |
| `update_event(uid, calendar?, summary?, start?, end?, location?, description?)` | Change fields; omitted fields are untouched, `""` clears location or description. Changing only `start` keeps the duration |
| `delete_event(uid, calendar?)` | Delete an event |

Events are identified by UID. Updating or deleting a recurring event acts on the **whole series**.
Times without an offset use the configured timezone, and times are returned in that timezone.
Errors are returned as plain strings (for example `event not found: 'abc'`).

## Security notes

- The app-specific password grants access to your calendars (and, to Apple, other iCloud
  services that accept app passwords). Keep it in an environment variable or a secret store.
- The SSE transport refuses to start without `MCP_BEARER_TOKEN` and does not terminate TLS.
- Use `ICLOUD_MCP_READ_ONLY=true` if the assistant should only read.
- Secrets are never logged. The container runs as a non-root user.

## Known limits

- Only calendars that support events are exposed; Reminders and other collections are ignored.
- Shared and subscribed calendars may be read-only or behave differently on iCloud's side; CalDAV
  errors are passed through as short messages.
- iCloud may rate-limit heavy use.
- Other CalDAV providers may work but are untested and unsupported.

## License

MIT, see [LICENSE](LICENSE).
