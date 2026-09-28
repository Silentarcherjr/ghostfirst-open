# ghostfirst-open

The open-source hackathon layer of [GhostFirst](https://52-45-211-166.sslip.io):
*evidence before the click*. GhostFirst sends a disposable remote browser to a
suspicious link and explains what it saw, before a person or an agent opens it.

The GhostFirst core (verdict engine, backend, and Android app) is private and
is reached over its public HTTP API. This repository contains only the
separable layers built on top of it.

| Folder | What it is | Status |
|---|---|---|
| [`mcp/`](mcp/) | MCP server: a link-safety gate for AI agents (`check_link`, `deep_check`) | Working |
| `explain/` | Grounded plain-language explanations with an NVIDIA Nemotron model | Planned |
| `lens/` | OpenCV checks (QR sticker overlay, visual timeline evaluation) | Planned |

Design rule for every layer: **AI explains, deterministic rules decide.**

License: Apache-2.0.
