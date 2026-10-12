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
