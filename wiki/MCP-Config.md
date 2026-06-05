# MCP Configuration

Run APEX Ngin2dos from Cursor via the MCP server.

## Cursor settings

Add to `.cursor/mcp.json` (or global MCP config):

```json
{
  "mcpServers": {
    "http2-bomb": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "/path/to/APEX-Ngin2dos",
      "env": {}
    }
  }
}
```

Use your cloned repo path for `cwd`. Activate venv in the command if needed:

```json
"command": "/path/to/APEX-Ngin2dos/.venv/bin/python"
```

## Available tools

| Tool | Purpose |
|------|---------|
| `probe_http2` | Safe HTTP/2 capability check |
| `run_http2_bomb_test` | Full benchmark (requires `authorization_confirmed=true`) |

## Authorization gate

Bomb tests require explicit confirmation:

```
authorization_confirmed: true
scope_description: "Local nginx lab on 127.0.0.1:8443"
```

## Variant parameter

Pass `variant` to select target stack: `nginx`, `httpd`, `envoy`, `pingora`, `iis`.

## Profiles

- `probe` — HTTP/2 check only
- `safe` — minimal connections
- `moderate` — lab-default
- `aggressive` — scaled apex (lab only)

See `SKILL.md` in the repo root for full MCP skill documentation.
