# Ghost Checkout

**Every agent can reach checkout. Ours cannot be talked into choosing a payee.**

E1–E5, built with mocks on 2026-10-13. Python 3.12 · Apache-2.0 · MCP 2.2.0.
No money moves, no credential is required and no provider is contacted.
Real sandbox/LLM wiring is **E6**, after Claude review and owner authorization.
There is no claim of a live payment, live AI session, or hackathon eligibility.

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
from the real APIMatic package; controller/HTTP calls remain mocked.

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

| API / SDK | Role | E1–E5 status |
|---|---|---|
| PayPal Python Server SDK 2.0.0 (APIMatic) | `OrderRequest` model; injected Orders/Payments controllers | Real model serialization tested; controller calls mocked |
| Orders v2 `POST /v2/checkout/orders` | Explicit observed `purchase_units[].payee.merchant_id`; CAPTURE intent | Mock create, no live OAuth/controller |
| Orders v2 `GET /v2/checkout/orders/{id}` | Read status; pre/post-capture payee and amount checks | Mock GET; fixed status output only |
| Orders v2 `POST /v2/checkout/orders/{id}/capture` | After buyer approval only | Mock capture; uncertain outcome stops without retry |
| Payments v2 `POST /v2/payments/captures/{id}/refund` | Refund known captures when verification fails | Mock refund, tested mismatch and refund failure |
| `POST /v1/notifications/verify-webhook-signature` | Verify before accepting APPROVED / CAPTURE.COMPLETED notifications | Mock REST transport, replay-bound; events never capture/approve |
| JS SDK v6 `createInstance`, eligibility, one-time payment session `start`/`onApprove` | Human approval UI | Local v6-shaped mock, no PayPal script/network |
| Classic JS SDK `/sdk/js?client-id=…&merchant-id=…` | Request-only merchant observation | Fake SDK URL fulfilled locally in scanner/Wisp-lite tests |
| MCP SDK 2.2.0 | Async session-owned checks, stateless check fallback, human elicitation, order tools | Actual pinned SDK, in-memory and stdio |
| PayPal Agent Toolkit / sandbox MCP / transaction search | Optional read-only additions | **Not used**; no sponsor/API claim for these |
| OpenAI-compatible chat/tool protocol | Provider-neutral orchestration interface | Mock transport only; Bedrock Converse is a stub |

Sources: [PayPal Server SDK](https://developer.paypal.com/serversdk/python/),
[Orders v2](https://developer.paypal.com/docs/api/orders/v2/),
[v6 upgrade](https://developer.paypal.com/v5-v6),
[v6 setup](https://developer.paypal.com/sdk/js/set-up/),
[official OpenAI tool-calling format](https://developers.openai.com/api/docs/guides/function-calling).

**SDK version limitation:** `/sdk/js` is classic, not v6. v6 core is
`/web-sdk/v6/core`, and that URL does not identify the merchant. Do not infer a
merchant from client-id or fixture query parameters on v6. The demos distinguish
mock classic observation metadata from the mock v6 approval UI. Real v6 merchant
observation and multiparty/sandbox payee authorization must be resolved in E6;
v6-only stores without merchant observation refuse.

## What is public, hosted, recorded and private?

- This directory alone contains the binding rules, MCP server, SDK adapter,
  orchestrator, UI, stores, mocks, Wisp-lite and tests. It imports no private
  GhostFirst module and needs no monorepo checkout.
- **Default runtime makes no hosted GhostFirst request.** Recorded data is in
  `demo_data.py`, labeled synthetic. Demo URLs use reserved `.test` names;
  the recorded client never resolves/fetches them.
- `api.py` defines the `/v1/scans` boundary used by the hosted GhostFirst API
  (`https://ghostfirst.com`), but E1–E5 require MockTransport. Actual hosted mode
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
connection close. Restart/expiry loses ownership; old orders cannot be resumed.
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

## Secrets and E6 handoff

`.env.example` contains blanks/placeholders only and is not auto-loaded. Runtime
accepts offline mode only; it **does not read credentials**. When separately
ready for E6, real sandbox secrets belong in `~/.config/ghostfirst/paypal.env`,
read server-side at runtime by the future authorized adapter. Do not put secrets
in the browser, model, Git or chat. A public JS client ID is distinct from a
client secret; no secret is present here. See [SECURITY.md](SECURITY.md).

Stop after E5 for Claude Code review. No live sandbox/LLM run, E6 wiring, deploy,
push, publication, cloud provisioning, video or Devpost submission is included.
