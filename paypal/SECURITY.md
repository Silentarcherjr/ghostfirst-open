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

Everything in E1–E5 uses mock PayPal, mock LLM and recorded synthetic API data.
There is no credential-reading/live-provider fallback. Future secrets belong in
~/.config/ghostfirst/paypal.env and never in Git, chat, browser, or model output.
Do not publish monorepo history; only the separately approved public export.
