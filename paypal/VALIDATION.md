# Local validation — 2026-10-13

## Offline suite

- Public Python 3.12 project: **69 passed**, including four opt-in Chromium
  390 px flows, in 8.05 s. Flash accept/decline, Corner mock capture and Riverside
  refusal; no external page requests, injected prose output, overflow or JS errors.
- Actual MCP sessions/elicitation/stdio, ownership and expiry; SDK models and
  mocked HTTP OAuth/create/get/capture/refund mapping; optional amount breakdown;
  payee/amount binding, refunds, uncertainty, guards, CSRF and UI contrast.
- External-secret parsing uses fake test values. Autouse guards force offline
  mode and block real requests/HTTPX transport. The real recorded OpenRouter
  cassette replays through MockTransport, without contacting a provider.
- Sandbox UI cannot use mock approval; capture before APPROVED refuses without
  calling capture. Empty webhook ID refuses before verification/network.
- Backend **377 passed** (175.73 s; existing LibreSSL/escape warnings); Flutter
  **224 passed**, analysis clean; original MCP **42 passed**; web contract
  **6 passed**. UI JavaScript syntax and Git whitespace checks passed.
- Previous E5 standalone install: 50 passed, 5 skipped. That historical result
  does not establish standalone coverage of the new E6 adapter.

Repeat from this directory after optional Chromium installation:

```sh
GHOST_CHECKOUT_BROWSER_TESTS=1 uv run --offline --extra test pytest -q
```

Use `GHOST_CHECKOUT_CHROMIUM=/absolute/path/to/Chromium` for an installed browser.
Without browser opt-in, four browser tests skip. The offline chat needs neither
Chromium nor keys. No physical accessibility study or genuine v6 approval test.

## Authorized external evidence

- One **1.00 USD sandbox** order created through the pinned APIMatic SDK with an
  explicit merchant observed on the local Corner fixture. OAuth token RAM only.
  Approval link printed only for the owner, no buyer login/approval automation.
- Real GET matched merchant/currency/value. A deliberately different expected
  merchant was rejected with **no capture**. SDK optional amount breakdown is
  tolerated without relaxing these immutable comparisons.
- Capture/refund were **not executed live**. The owner manually approves and
  resumes the smoke CLI as documented in README; refund uses a fresh order.
- One real OpenRouter conversation: six calls, reported USD **0.0010817**.
  Three store checks; every episode stopped without start_checkout/order.
  The model was conservative. Initiation wording was clarified afterwards, not
  rerun live. Page injection text was never sent to the model by construction.
- Public cassette contains sanitized requests/responses and synthetic store IDs;
  the monorepo trace is in research/ghost_checkout_trace. Replay tests validate
  recorded transport/guards, not the behavior of the revised prompt.
- Webhook ID remains empty; no real webhook/signature verification performed.
  Hosted GhostFirst mode disabled; fixture Wisp-lite is not the private engine.

No deployment, push, publication or cloud resource creation. Codespaces remains
prepared configuration only. Credentials, real order IDs and approval links are
excluded from committed evidence. Local `uv build --offline` produced wheel/sdist; runtime UI/store resources and
smoke/trace scripts plus cassette inclusion were checked. Packaging tests: 4 passed.
No artifact is published.
