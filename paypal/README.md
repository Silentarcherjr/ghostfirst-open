# Ghost Checkout (E3 — mocks first)

Python 3.12, MCP SDK 2.2.0, Apache-2.0. The agent never chooses a payee.
Only an observed PayPal merchant can be bound into Orders v2; page prose is
excluded and missing merchants refuse. All provider calls are mocked.

Current tools: check_store, get_check_result, start_checkout, complete_checkout,
order_status. start_checkout has no payee argument. Human elicitation chooses
only among observed merchants, and buyer approval remains a separate UI step.
Connection-owned checks cache for less than ten minutes. Stateless checks run
inline; stateless mutations refuse without verified ownership. Disconnect
clears owned state. Unknown/expired orders and uncertain captures fail closed.

APIMatic paypal-server-sdk 2.0.0 models are exercised offline, and a small
controller adapter supports create/get/capture/refund. SDK OAuth/live controllers
are not wired. Signature verification uses an injected mock REST transport;
verified webhooks are advisory and never approve/capture by themselves.

Local tests (no credentials): `uv run --extra test pytest -q`.
The complete offline agent/UI runner and judge setup are E4–E5.
