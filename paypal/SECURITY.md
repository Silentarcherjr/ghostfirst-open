# Payment and model boundary

Rules decide. No payee argument exists. An observed merchant ID is not proof of
identity or fulfilment; a client ID is never a merchant fallback. Page prose,
claim text and provider errors never enter model/tool output. Multiple merchants,
caution or a claim mismatch needs human elicitation, with selection constrained
to observed IDs. Missing merchant or do-not-continue refuses.

Orders are bound to the verified session and the observed merchant. Buyer
approval is human-only. Capture prechecks APPROVED/payee/amount, then GET checks
payee/amount again. Known captures on mismatch refund; uncertainty stops and
never automatically retries. Orders/cache/state are bounded volatile RAM.
Restart/disconnect loses bindings; do not reuse old provider order IDs.

MCP stateless checks run inline, but mutations require a verified connection.
The offline UI has server-issued sessions. Webhook verification precedes event
handling, events are deduplicated and advisory, never automatic approvals.

Offline mode never reads credentials or contacts providers. Explicit sandbox
mode accepts only the fixed PayPal sandbox and OpenRouter HTTPS origins, disables
redirects/proxies and SDK logging, and retains OAuth only in RAM. Secrets are
read from an owner-owned 0600 regular file outside the repo; errors are fixed.
No credential is sent to Flutter or persisted in a transcript. Redacted model
messages and sanitized provider responses are used for the recorded cassette.

Buyer approval remains human-only. The approval redirect is supplied only to
the owner's UI, never to a model tool. Sandbox refuses simulated approval.
The owner-only smoke CLI can resume an explicitly supplied order only after
fresh local fixture observation and GET payee/amount/status checks; normal
UI/MCP bindings still expire and cannot be recovered after restart.

OpenRouter has six-call/token/context/price/cost caps, no retries or provider
fallback. Page prose is excluded by construction, not trusted after model review.
The real recorded model was conservative and did not start checkout; it is not
proof of complete autonomous payment. Capture/refund and signature verification
are wired but not verified live; an empty webhook ID refuses before network.

Never publish monorepo history; only a separately approved public export.
