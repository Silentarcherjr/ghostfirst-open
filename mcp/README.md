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

## Try it (judges)

**Hosted:** open <https://mcp.ghostfirst.com> (the simulator; MCP endpoint
`https://mcp.ghostfirst.com/mcp`).

**Locally, against the hosted GhostFirst API** (needs
[uv](https://docs.astral.sh/uv/); uv downloads Python 3.12 if needed):

```bash
git clone https://github.com/Silentarcherjr/ghostfirst-open.git
cd ghostfirst-open/mcp
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[test]"
.venv/bin/ghostfirst-mcp --http
```

Then open <http://127.0.0.1:8780/> in a browser. The simulator connects to
the local server, which calls `https://ghostfirst.com` (the default
`GHOSTFIRST_API_URL`), so no account or key is needed. Type or say, for
example:

1. `Is this link safe? https://52-45-211-166.sslip.io/changes-face.html`
   — a labeled demo page that turns into a sign-in form after loading. The
   answer is "be careful" and offers to look again; say or type "yes" to
   run `deep_check`.
2. `https://52-45-211-166.sslip.io/steady.html` — an ordinary page; the
   answer is "no obvious danger" (never "safe").
3. `https://52-45-211-166.sslip.io/waits-for-you.html` — the form appears
   only after a visitor moves the pointer or scrolls.
4. `https://52-45-211-166.sslip.io/reset?token=demo123` — looks like a
   one-time link, so the server asks **you** (Yes/No) before anything is
   sent. Answer No and nothing is visited.

The demo pages are listed at <https://52-45-211-166.sslip.io/>; they are
brand-free and labeled as tests. The "MCP traffic" panel shows every MCP
message (`initialize` with protocol 2025-11-25, `tools/call`,
`elicitation/create`). The hosted API is rate-limited; if the answer says
GhostFirst is busy, wait and try again.

## Run

Tested with Python 3.12 (the package declares `>=3.10`).

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[test]"
.venv/bin/ghostfirst-mcp            # stdio transport
.venv/bin/ghostfirst-mcp --http     # Streamable HTTP on http://127.0.0.1:8780/mcp
```

`--http` options:

| Flag | Default | Meaning |
|---|---|---|
| `--host` | `127.0.0.1` | Address to bind |
| `--port` | `8780` | Port to bind |
| `--allowed-host HOST` | none | Public `Host` name to accept; repeatable; required when `--host` is not local |
| `--no-simulator` | off | Serve only `/mcp`, without the simulator page |

### Streamable HTTP and the voice simulator

`--http` serves MCP (protocol 2025-11-25 and later) at `/mcp` with stateful
sessions, so the one-time-link question still reaches the human: the
`elicitation/create` request travels on the open `tools/call` stream.

The same server also serves **GhostFirst Voice Check** at `/`: a simulated
voice assistant (Alexa+ style) that is a real MCP client. It runs
`initialize`, `tools/list`, and `tools/call` over Streamable HTTP, shows the
traffic, and speaks the answers (browser speech synthesis; voice input where
the browser supports speech recognition). The page decides nothing: it turns
the server's fixed sentences into speech, and asks the human Yes/No when the
server asks. It loads nothing from other sites (strict CSP, same origin).

Off localhost, name every public host name:

```bash
.venv/bin/ghostfirst-mcp --http --host 0.0.0.0 --allowed-host mcp.example.org
```

Requests with any other `Host` header, or from any other browser origin, are
refused with 403 (DNS-rebinding protection). The accepted browser origin is
`https://<allowed host>`, so serve the simulator over HTTPS at that name.

A container image is included (`Dockerfile`); put a TLS proxy in front:

```bash
docker build -t ghostfirst-mcp .
docker run -p 127.0.0.1:8780:8780 -e MCP_HOSTNAME=mcp.example.org ghostfirst-mcp
```

Public instance: <https://mcp.ghostfirst.com> (simulator) and
`https://mcp.ghostfirst.com/mcp` (MCP endpoint).

`GHOSTFIRST_API_URL` selects the GhostFirst API. It must be `https`; plain
`http` is accepted only for localhost. The default is the hosted API,
`https://ghostfirst.com`.

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

The simulator's voice input uses the browser's own speech recognition; some
browsers send the audio to their vendor's speech service. Typing avoids
that.

## Test

```bash
.venv/bin/python -m pytest -q
```

The tests use a fake API, so they make no network calls (19 tests). The
server tests drive the real MCP client in memory; the HTTP tests run the
Streamable HTTP app on a local port. They cover:

- the output shape;
- that page-controlled text is excluded;
- the one-time-link consent paths: not asked, accepted, declined, and
  detected by the API;
- typed errors;
- over HTTP: a browser-style client, the human question on the same stream,
  refused foreign hosts, the simulator's strict policy, and the
  `--allowed-host` requirement off localhost.
