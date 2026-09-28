# GhostFirst MCP server

An MCP server that lets an AI agent **check a link with GhostFirst before it
opens or follows it**. GhostFirst sends a disposable remote browser (a *Wisp*)
to the link, away from the agent's machine and the user's device. It returns
a verdict with the evidence behind it.

Deterministic rules decide the verdict. This server only reshapes the API
result for agents. No model output can set or change a verdict.

## Tools

| Tool | What it does | Typical time |
|---|---|---|
| `check_link(url)` | Visits the link once. Returns `verdict` (`do_not_continue`, `caution`, `no_obvious_danger`), `reasons`, `agent_guidance`, and `recommended_next_step` | 5–10 s |
| `deep_check(url)` | Visits as a phone, a computer, and another browser, and reports whether they were shown different things (cloaking) | 10–20 s |

Both tools are read-only and take only `url`.

## Safety design

- **No page-controlled text reaches the agent.** Page titles, page text,
  event messages, and full URLs are dropped. Only fixed sentences are
  returned, filled with host names (in ASCII/punycode, so look-alike
  characters stay visible), brand names from GhostFirst's registry, and
  counts. A malicious page therefore cannot write instructions into the
  agent's context through this server.
- **One-time links are never visited on the agent's say-so.**
  - Password-reset, sign-in, and invitation links are detected before
    anything is sent.
  - The server then asks the **human** through MCP elicitation. The agent
    has no argument it could use to confirm on the human's behalf.
  - If the client cannot ask the human, the link is not visited.
  - The GhostFirst API applies the same rules again.
- **Errors fail closed.** Every error tells the agent not to open the link.
- `no_obvious_danger` is never presented as "safe". Every result carries
  `not_a_guarantee`.

## Run

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[test]"
.venv/bin/ghostfirst-mcp            # stdio transport
```

`GHOSTFIRST_API_URL` selects the GhostFirst API. It must be `https`; plain
`http` is accepted only for localhost. The default is the hosted staging API.

Example client configuration (for example, Claude Desktop):

```json
{
  "mcpServers": {
    "ghostfirst": {
      "command": "/path/to/ghostfirst-open/mcp/.venv/bin/ghostfirst-mcp"
    }
  }
}
```

## Privacy

The link you check is sent to the GhostFirst API, which opens it in an
isolated remote browser. Screenshots expire automatically, and no check
history is stored. This server keeps nothing.

## Test

```bash
.venv/bin/python -m pytest -q
```

The tests drive the real MCP client in memory against a fake API. They cover:

- the output shape;
- that page-controlled text is excluded;
- the one-time-link consent paths: not asked, accepted, declined, and
  detected by the API;
- typed errors.
