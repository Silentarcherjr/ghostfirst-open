# Ghost Checkout

**Every agent can reach checkout. Ours cannot be talked into choosing a payee.**

Built on 2026-10-13. Python 3.12 · Apache-2.0 · MCP 2.2.0.
**Offline is the default:** no credential or provider request. E6 adds an explicit
sandbox-only PayPal adapter and bounded OpenRouter tool calling. One real sandbox
order was created and read; buyer approval, capture and refund remain owner steps.
One real OpenRouter conversation is recorded with its limitations below.

## Run the offline demo

From this directory, install [uv](https://docs.astral.sh/uv/) and Python 3.12:

```sh
uv sync --extra test --frozen
uv run --offline ghost-checkout-demo
```

Open **http://127.0.0.1:8876**. After dependency setup, the demo runs completely
offline: deterministic mock model, mock PayPal, recorded **synthetic** GhostFirst
API responses, local JS SDK v6-shaped mock. No API key, .env file, DNS request
to a demo store, or Chromium is needed for the chat demo. The SDK models come
from the real APIMatic package; controller/HTTP calls in this default mode remain mocked.

Codespaces: open this folder using `.devcontainer`, then:

```sh
uv run --offline ghost-checkout-demo --host 0.0.0.0
```

Keep forwarded port 8876 **private**. The configuration file does not create a
Codespace/resource or deploy anything. This local mock server is not a production
hosting recipe. An optional Render deployment is intentionally not configured.

## Judge walkthrough (all mock)

1. **Flash Sale, the hero scene.** Inspect `/shop/flash-sale.html`: visible
   `DEMO_CLAIMED_MERCHANT`, SDK observation fixture `DEMO_OBSERVED_MERCHANT`,
   hidden text asking assistants to pay `INJECTED_ACCOUNT_X`.
2. Start a fresh chat session, choose Flash Sale, enter the item and exact amount,
   then ask the assistant to check and buy. The model chooses check_store and
   start_checkout; it cannot change the purchase mandate or supply a payee.
3. Expand **Why?** and **Developer · MCP traffic**. The verdict/evidence is fixed.
   The tool has no payee argument and no page prose appears in traffic/model input.
   The recorded engine verdict stays calm; the independent merchant-claim mismatch
   still requires human checkout review. That does not rewrite the engine verdict.
4. Human merchant confirmation appears. Declining creates no order. Continuing
   binds `purchase_units[0].payee.merchant_id` to `DEMO_OBSERVED_MERCHANT`.
5. Click **Open simulated PayPal approval**, then approve in the labeled mock
   dialog. The agent cannot click this human action. Capture is followed by GET
   and payee/amount verification. The UI says “Mock capture verified. No real payment.”
6. Start a fresh session for **Corner Bakery** (calm check → human payment step)
   or **Riverside Deals** (late offsite-card evidence → missing merchant → refusal).
   Its standalone store page reveals a card form after two seconds and never submits.

Developer trace is actual in-memory MCP SDK traffic, not a canned transcript.
Recorded verdicts are contracts from synthetic scenarios, not live field results.
The hidden injection is illustrative; it is not given to the mock model at all.
Mismatch refunds and provider/API failures are tested, not claimed as live demos.

## PayPal API and SDK inventory

| API / SDK | Role | Current evidence |
|---|---|---|
| PayPal Python Server SDK 2.0.0 (APIMatic) | Orders/Payments models and controllers; RAM-only OAuth cache | Actual sandbox OAuth, create and GET; full mapping tested with mocked HTTP |
| Orders v2 `POST /v2/checkout/orders` | Explicit observed `payee.merchant_id`, CAPTURE intent | One real 1.00 USD sandbox order created; approval pending human |
| Orders v2 `GET /v2/checkout/orders/{id}` | Status, pre/post-capture payee and amount | Real read and deliberate expected-merchant mismatch refusal, no capture |
| Orders v2 `POST /v2/checkout/orders/{id}/capture` | APPROVED/payee/amount precheck, human step | Wired; tested offline, not executed against sandbox |
| Payments v2 `POST /v2/payments/captures/{id}/refund` | Known-capture mismatch compensation / owner smoke | Wired; tested offline, not executed against sandbox |
| `POST /v1/notifications/verify-webhook-signature` | Verify before advisory event handling | Sandbox OAuth helper wired; empty webhook ID refuses before network; mock tests only |
| JS SDK v6 payment session | Human approval in offline demo | Local v6-shaped mock; genuine v6 integration unresolved |
| Classic JS SDK `/sdk/js` | Request-only merchant observation | Local fixture request intercepted and fulfilled locally; sandbox fixture renders runtime IDs in RAM |
| Sandbox approval redirect | Owner browser only, never a model tool result | Validated sandbox link obtained; no automated login or approval |
| MCP SDK 2.2.0 | Owned checks, elicitation and order tools | Actual pinned SDK, in-memory and stdio |
| OpenRouter tool calling, Claude Haiku 5.5 | Guarded orchestration | One real conversation, six requests; recorded offline replay |
| PayPal Agent Toolkit / transaction search / Bedrock | Optional alternatives | Not used; Bedrock remains a stub |

Sources: [PayPal Server SDK](https://developer.paypal.com/serversdk/python/),
[Orders v2](https://developer.paypal.com/docs/api/orders/v2/),
[v6 upgrade](https://developer.paypal.com/v5-v6),
[v6 setup](https://developer.paypal.com/sdk/js/set-up/),
[official OpenAI tool-calling format](https://developers.openai.com/api/docs/guides/function-calling).

**SDK version limitation:** `/sdk/js` is classic, not v6. v6 core is
`/web-sdk/v6/core`, and that URL does not identify the merchant. Do not infer a
merchant from client-id or fixture query parameters on v6. The demos distinguish
mock classic observation metadata from the mock v6 approval UI. Real v6 merchant
observation and genuine v6 approval remain unresolved. Sandbox E6 uses the
classic local fixture observation and a human approval redirect; v6-only stores
without merchant observation refuse.

## What is public, hosted, recorded and private?

- This directory alone contains the binding rules, MCP server, SDK adapter,
  orchestrator, UI, stores, mocks, Wisp-lite and tests. It imports no private
  GhostFirst module and needs no monorepo checkout.
- **Default runtime makes no hosted GhostFirst request.** Recorded data is in
  `demo_data.py`, labeled synthetic. Demo URLs use reserved `.test` names;
  the recorded client never resolves/fetches them.
- `api.py` defines the `/v1/scans` boundary used by the hosted GhostFirst API
  (`https://ghostfirst.com`), but the demo uses MockTransport. Actual hosted mode
  is disabled. The full engine, isolated Wisp, Replay/CAU-9 and reputation remain
  private/hosted; they are **not** bundled or reproduced by Wisp-lite.
- Wisp-lite shows public request capture and card presence on the fixed local
  demo fixtures. It is not a full verdict, does not implement OpenCV/cloaking,
  and has no arbitrary URL/live mode. No field accuracy/security-isolation claim.

Optional public observer (one-time browser install needs internet):

```sh
uv run playwright install chromium
uv run --offline ghost-checkout-wisp-lite
```

It starts its own loopback fixture server, rewrites the synthetic SDK observation
request to the exact classic PayPal URL, fulfills it locally, and blocks every
other external request. Results contain bounded IDs/booleans only; no page prose,
input value, screenshot, cookie or token. No click, typing or form submission.
For an already installed local Chromium, set `GHOST_CHECKOUT_CHROMIUM` to its
executable path instead of installing another browser.

## Tools and payment boundaries

- `check_store(store_url)` / `get_check_result(job_id)`: complete fixed evidence,
  observed merchant IDs (or none). Connection checks are asynchronous; checking
  is not a verdict. Stateless clients get the check inline.
- `start_checkout(store_url, item, amount, currency)`: **no payee argument**.
  Same-session exact-URL checks younger than ten minutes can be reused.
  DNC refuses; missing merchant refuses; caution, multiple merchants or a claim
  mismatch asks the human. Human selection must belong to the observed set.
- `complete_checkout(order_id)`: owned order, human approval, precheck, capture,
  GET assertion, known-capture refund on failure. Ambiguous create/capture/refund
  stops for manual review; no automatic retry/repeated capture.
- `order_status(order_id)`: read-only, same owner, fixed statuses only.
- `/paypal/webhook`: bounded signature verification before event dispatch.
  Mock server accepts only the explicit `MOCK-VALID-SIGNATURE` test marker;
  this is **not real signature validation**. Events are advisory and deduplicated.

State is bounded volatile RAM: cache 10 min, order/session 15 min, cleanup on
connection close. Restart/expiry loses UI/MCP ownership. The separate owner-only smoke CLI can
resume an explicitly supplied order after fresh fixture observation and GET checks.
Stateless **payment mutations refuse** because verified session ownership is
unavailable. The UI uses a server-issued session and a stateful MCP client.
The model only selects tools/phrases answers. Amount/item/currency come from the
person's exact mandate. Fixed verdicts/payees are never parsed from model prose;
output guard rejects “safe”/approval claims. Approval is a separate human UI
boundary. The offline mock UI is not an authentication/payment-security product.

## Validate

```sh
uv run --offline --extra test pytest -q
```

Tests cover actual MCP sessions/elicitation, injected SDK controllers, payee and
amount binding, no prose/injected account output, refund failures, API/provider
errors, uncertain capture, ownership/cache expiry, output guard, Origin/CSRF and
HTTP UI flow. Browser verification checks a 390 px phone viewport and blocks
external requests. Run it with `GHOST_CHECKOUT_BROWSER_TESTS=1` after the optional
Chromium setup (or `GHOST_CHECKOUT_CHROMIUM` for an existing binary). See `VALIDATION.md` for measured results.

## Explicit sandbox mode and owner smoke

Secrets stay in an owner-owned **0600**, regular, non-symlink file outside this
repository: `~/.config/ghostfirst/paypal.env`, or `GHOST_CHECKOUT_SECRETS`.
The reader never evaluates shell code. Required names are `PAYPAL_CLIENT_ID`,
`PAYPAL_CLIENT_SECRET`, `SANDBOX_MERCHANT_ID`, `LLM_API_KEY`, `LLM_MODEL`;
`LLM_BASE_URL` must be `https://openrouter.ai/api/v1` and the current model is
`anthropic/claude-haiku-5.5`. `PAYPAL_WEBHOOK_ID` stays empty until owner setup.
`.env.example` is blank documentation, never auto-loaded. Offline mode does not
read the external file. Non-sandbox PayPal modes/base URLs fail closed.

From this directory, with local Chromium installed:

```sh
GHOST_CHECKOUT_MODE=sandbox uv run python tool/sandbox_smoke.py --action create
GHOST_CHECKOUT_MODE=sandbox uv run python tool/sandbox_smoke.py --action mismatch --order-id ORDER_ID
```

Set `GHOST_CHECKOUT_CHROMIUM` to an installed executable if needed. Creation
observes only the locally served Corner Bakery fixture, binds the runtime merchant
and 1.00 USD, prints only the order ID and sandbox approval link, then exits at
the human boundary. The second command performs GET and rejects a deliberately
wrong expected merchant; it never captures. Neither command calls OpenRouter.

**Owner only:** open the printed link yourself, log in with your sandbox buyer
and approve manually. Then resume that order:

```sh
GHOST_CHECKOUT_MODE=sandbox uv run python tool/sandbox_smoke.py --action capture --order-id ORDER_ID
```

For capture-then-refund coverage, create a **fresh second order**, approve it
manually, then run `--action refund --order-id ORDER_ID`. Both actions require
APPROVED and matching observed merchant/amount; an already captured order cannot
be reused. Ambiguity prints a fixed failure and requires manual review, never an
automatic retry. Capture/refund were not run live during E6.

```sh
GHOST_CHECKOUT_MODE=sandbox uv run ghost-checkout-demo
```

Sandbox UI binds to loopback only and offers only Corner Bakery. It uses local
fixture observation, real OpenRouter and real sandbox Orders. The owner opens
the approval link with a button, manually approves in PayPal, then explicitly
requests verification/capture. The simulated approval endpoint refuses sandbox
clients. No credential or approval link enters the model. This is a local test
boundary, not arbitrary-store browsing or the hosted private engine.

OpenRouter is capped at six calls per process, 384 completion tokens/call,
40,000 context characters, explicit provider price ceilings and a USD 0.10
reported-cost stop. No retry/fallback. The one authorized recorded conversation
cost **USD 0.0010817** across six calls: all three stores stopped after checks,
without `start_checkout` or even a mock order. Corner requested additional human
confirmation. The initiation prompt was clarified afterwards and has **not**
been tested again with a real provider. The trace proves transport/guard behavior,
not complete autonomous checkout or model resistance to page injection: page
prose never enters the model by construction. The cassette is in
`tests/cassettes/openrouter_conversation.json`; monorepo evidence is in
`research/ghost_checkout_trace/`. The trace runner refuses an existing output;
do not rerun paid sessions without fresh owner authorization.

For webhooks, the owner must first arrange an independently authorized public
HTTPS endpoint, register PayPal sandbox events and add its webhook ID to the
external secret file. Empty ID stops before verification/network. No endpoint
was deployed or registered; no real webhook was received. Notifications remain
advisory and never substitute for buyer approval.

See [SECURITY.md](SECURITY.md) and [VALIDATION.md](VALIDATION.md). E6 is local and
awaits Claude Code review. No deploy, push, publication or cloud provisioning.
