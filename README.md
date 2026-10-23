<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="brand/ghostfirst-lockup-dark.png">
    <img src="brand/ghostfirst-lockup-light.png" alt="GhostFirst" width="360">
  </picture>
</p>

# ghostfirst-open

The open-source hackathon layer of [GhostFirst](https://ghostfirst.com):
*evidence before the click*. GhostFirst sends a disposable remote browser to a
suspicious link and explains what it saw, before a person or an agent opens it.

The GhostFirst core (verdict engine, backend, and Android app) is private and
is reached over its public HTTP API. This repository contains only the
separable layers built on top of it.

| Folder | What it is | Status |
|---|---|---|
| [`mcp/`](mcp/) | MCP server: a link-safety gate for AI agents and voice assistants (`check_link`, `deep_check`, `get_check_result`, `check_shared_link`), human-only consent, EN/es-US voice and inline MCP Apps card, over stdio or Streamable HTTP, with a voice-assistant simulator | Working; the same code is live at <https://mcp.ghostfirst.com> |
| `lens/` | OpenCV checks (QR sticker overlay, visual timeline evaluation) | Planned |

Design rule for every layer: **AI explains, deterministic rules decide.**

**Try Task A locally:** run the offline fixture server or the MCP server and its
voice-assistant simulator locally in a few commands; see
[`mcp/README.md` → Try it](mcp/README.md#try-it-judges).

The simulator has a session-only shared-links inbox: Share, ask without URL
dictation, then hear complete evidence or use the card. Jobs acknowledge
quickly and are polled; deterministic verdicts never come from AI. No OAuth,
caregiver service or real Echo bridge is connected.

Issues and pull requests are welcome.

License: [Apache-2.0](LICENSE). The license covers the code; the GhostFirst name and logo (`brand/`) are not licensed for use as your own branding.
