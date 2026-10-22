# Local accessibility review — Task A (2026-10-11)

Scope: the simulator and inline MCP Apps card in Chromium, with the offline
`tool/fake_ui_server.py` MockTransport fixture. No provider visit, live Alexa
surface, microphone audio, or vendor speech service was used. `axe-core` was
not resolvable locally (`require.resolve('axe-core')`); no package was fetched.
This is a targeted browser and manual review, not an axe or certification pass.

Reproduce from the monorepo root (existing backend Playwright environment):

```bash
(cd ghostfirst-open/mcp && .venv/bin/python tool/fake_ui_server.py)
backend/.venv/bin/python ghostfirst-open/mcp/tool/check_accessibility.py
```

For the standalone public subtree, run the second script with a Python
environment that already has Playwright and Chromium installed. The fixture
server listens only at 127.0.0.1:8799 and never contacts the real API.

| Check | Result |
|---|---|
| 375 × 812 viewport, light/dark | Shared inbox, card and transcript render; no page errors |
| 200% zoom at 375 px | No document horizontal overflow in either theme (one-pixel rounding tolerance); MCP headings and share status wrap |
| Contrast, computed text/background | Lowest tested ratio 5.45:1 light / 6.22:1 dark, including all three verdict colours, muted text and primary buttons |
| Target sizes | Main buttons ≥49 px tall; locale selector 48 px; card Yes/No 80 × 51 px; checkbox has a ≥48 px clickable label |
| Labels and focus | Inputs have labels; mic has a name; frame has a title; native buttons/select and visible focus outlines |
| Keyboard | Focus card No, Enter cancels follow-up; focus Yes succeeds; Spanish typed “sí” starts Deep Check |
| Spoken fallback | Captured es-US utterance contains verdict, summary, evidence, final host and disclaimer without needing the frame; mic language es-US |
| Session continuity | Share → check without dictating URL → repeat adds fixed history sentence → Deep Check |
| Malicious page imagery | No images, screenshots or page HTML in the card |

Manual visual/semantic review: host is large and wraps, verdict includes an
icon and text as well as colour, chips use fixed sentences, actions name the
single visible question. Reading order follows the DOM; transcript and card
announce updates through polite live regions. Ring motion respects reduced
motion and has no flashing state. Touch and written/voice responses both
reach the same consent/follow-up logic; the Share action is the phone-side
prerequisite, not an Alexa skill.

Still requires owner/device review: VoiceView and a screen reader with an
actual audio device, native Alexa integration, real Echo Show distances,
voice recognition quality and older-adult usability. Local browser checks
cannot establish those outcomes.

## Task G offline recheck — 2026-10-21

Run the same fixture and accessibility command above, then:

```bash
backend/.venv/bin/python ghostfirst-open/mcp/tool/walk_demo.py
```

(The `backend/.venv` path is the existing monorepo Playwright environment;
standalone users can use their installed Playwright Python environment.)

Task G adds a shared structured-evidence visitor renderer for the simulator's
sandboxed card and MCP Apps resource. Desktop has three columns; narrow cards
stack the tiles. Difference markers use a dashed coloured border plus `≠` and
fixed text. Reached/unavailable states include icons and text. Fixed field chips
have no actions. The frame reports intrinsic card height; transcript scrolling
honours reduced motion. CSP hashes and `sandbox="allow-scripts"` remain intact.

Fresh targeted checks: both themes, 375 px, 200% CSS zoom, no horizontal
overflow in the page or nested card; contrast minima remain 5.45:1 / 6.22:1;
controls ≥48 px. The EN/es-US walk covers all three tiles, punycode, missing
visitors, majority/all-different highlighting, typed and mocked recognised
voice follow-ups, all verdict guidance branches, no-result and unknown input,
and zero network requests for follow-ups. Desktop columns are asserted too.
Screenshots and `walk.json` are in `/tmp/ghostfirst-task-g/` (scratch only).
Viewport captures are used because this Chromium build produced blank iframe
element captures. Speech recognition/synthesis are mocked, not live audio.
These checks remain targeted review, not axe, certification or device evidence.
