# Local validation — 2026-10-13

Everything below uses mock PayPal/LLM and local or recorded synthetic inputs.
No real credential/provider/hosted API session, deployment or publication.

- Public Python 3.12 project: **55 passed** with opt-in Chromium browser tests.
  Includes actual MCP 2.2.0 sessions, async checks, stateless fallback, human
  elicitation, stdio entrypoint, owner isolation, cache expiry, fixed output,
  APIMatic model serialization and operation mapping, mismatch refunds, failures,
  uncertain/malformed capture, purchase/output guard, Origin/CSRF and UI contrast.
- Four 390 px Chromium flows: Flash Sale accept and decline, Corner Bakery mock
  capture and Riverside refusal with no order. No external page requests,
  page injection text in tool output, horizontal overflow or JS errors.
- Browserless standalone copy, frozen offline install: **50 passed, 5 skipped**.
  Four browser tests require explicit opt-in; the private checkout/store drift
  test is skipped in the independent export. No monorepo import is needed.
- Public Wisp-lite: three actual local fixture visits. Corner merchant matches
  recorded contract; Flash merchant differs from its bounded claim; Riverside
  has no SDK and its card form appears late. SDK URL fulfilled before network,
  other external requests blocked, isolated-world reads, no submit/click/typing.
  This is observation evidence, **not** the full private verdict/OpenCV engine.
- `uv build --offline`: wheel + sdist successful. Wheel contains the independent
  runtime, UI, stores and Apache license. No publish command was run.
- UI text color pairs ≥4.5:1; 48 px controls/ARIA log/self-only CSP/no innerHTML.
  No physical-user accessibility study or genuine PayPal approval UI test yet.

Repeat the complete public suite after Chromium installation:

```sh
GHOST_CHECKOUT_BROWSER_TESTS=1 uv run --offline --extra test pytest -q
```

Use `GHOST_CHECKOUT_CHROMIUM=/absolute/path/to/Chromium` for an already installed
browser; otherwise `uv run playwright install chromium` is a one-time setup.
The chat demo itself needs no browser binary and no network after dependency setup.

Private checkout integration (outside this independent package): backend/Flutter/
web/MCP validation and real Wisp evidence are recorded in the monorepo HANDOFF.
Codespaces JSON is prepared and validated, but no cloud instance was created.
All temporary screenshots/copies were removed after verification.

E6 remains pending: genuine sandbox SDK/OAuth, real v6 merchant observation,
merchant authorization, live webhook verification, hosted engine and LLM provider.
Do not present mocks as a completed payment or AI/provider session.
