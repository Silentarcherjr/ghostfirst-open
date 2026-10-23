# Friction log — GhostFirst Voice Check (Amazon Build, Ship, Shape · Alexa+ track)

What we tried, what happened, and what would have helped. Only first-hand
incidents from building this entry (Sep–Oct 2026), plus a dated
documentation review that is marked as such.

## Incidents

| Task | Steps taken | Expected vs. actual | Severity | Workaround | Suggestion |
|---|---|---|---|---|---|
| Test the MCP server on a real Alexa+ surface | Read the Alexa+ add-on docs; looked for MCP Toolkit / Web Simulator access | Expected a way to connect a self-hosted MCP server; the tools are partner-only | High | Built a simulated assistant that is a real MCP client (shows the protocol traffic on screen) | A public sandbox, even text-only, that accepts a self-hosted MCP URL |
| Human confirmation from a browser client | Built a JavaScript client; the server asks via `elicitation/create` in the middle of a tool call | Expected docs on answering a server request during an SSE stream from the browser; found none | Medium | Read the spec and SDK source; the client answers on the same session | A minimal browser MCP client example with elicitation |
| Serve the MCP server over HTTPS behind Caddy on EC2 | Same Caddy site settings as the main domain (`encode zstd gzip`, `reverse_proxy` with `flush_interval -1`); asked the simulator about a one-time link | Expected the Yes/No question mid-call; for gzip-capable clients it arrived only when the tool call ended, so the call appeared to hang | High | Removed `encode` from the MCP site | MCP hosting docs could warn that proxies must not compress `text/event-stream` responses |
| Redeploy the edge after adding the MCP host | `systemctl reload-or-restart caddy` (Caddy 2.6.2 from the Ubuntu package) | Expected a hot reload; Caddy panicked during the reload, so the edge was not reliably up | Medium | Deploy script falls back to a full restart and checks `systemctl is-active caddy` | Ship a newer Caddy in the distribution, or document the restart fallback |
| SSH into the EC2 instance to deploy | Ran the usual deploy command | Expected to connect; SSH timed out because the home IP had rotated and the security group allows SSH from one IP only | Medium | EC2 console → security group → edit the SSH inbound rule → "My IP" | Show "your IP is not in this security group" on the console's connect page, or offer a connection path that does not depend on the client IP |
| Pay for hosting with hackathon credit | Looked for the hackathon AWS credit code | Expected a code for registered builders; the codes had run out by Oct 7 | Low | Used the account's AWS Free Tier credit | State on the hackathon page when credit codes run out |

## Documentation review (2026-10-11, not a cloud or partner test)

| Task | Observation | Severity | Our response | Suggestion |
|---|---|---|---|---|
| Plan OAuth discovery | Alexa's [MCP Toolkit QuickStart](https://developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html) excludes `WWW-Authenticate` on 401, while [MCP authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization) describes header and well-known metadata discovery | Medium | Authentication left unimplemented; we do not claim a tested OAuth failure | A worked Alexa-compatible protected-resource-metadata example that explains the header limitation |
| Fit a browser visit into the latency requirement | The same QuickStart sets <500 ms round trips; its performance section has no job/polling example for long-running visits | High | Async acknowledgements plus session-scoped polling; local p95 measurements in `mcp/README.md` | Document whether acknowledgement plus polling qualifies, and how progress should be presented by voice |
