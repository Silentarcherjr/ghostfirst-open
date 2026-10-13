# Contributing

Use Python 3.12 and uv. Run `uv sync --extra test --frozen`, then
`uv run --offline --extra test pytest -q`. Keep all tests offline and fail closed.
Use injected SDK controllers/HTTP transports, never real keys or paid sessions.
Do not import private GhostFirst engine modules into this public package.

Never add a payee, merchant override, approval boolean or agent-confirmation
argument to payment tools. Human choices must be constrained to observed IDs.
Keep output fixed/allowlisted, render with textContent, and preserve ownership,
expiry, refund/uncertainty behavior and the no automatic retry policy.

Do not commit .env files, credentials, screenshots, cookies or signed URLs.
Report security issues privately to the project owner rather than publishing
exploit data. Publishing/deployment/provider runs require separate owner approval.
