# Owner-only integrations — unconnected designs

Task A7, 2026-10-11. None of these designs has runtime code, credentials,
resources, SDK dependencies or a configured connection. They are skipped
until the owner explicitly requests and provisions them.

| Integration | Proposed boundary | Owner prerequisite / remaining proof |
|---|---|---|
| SES caregiver notice | After a strong deterministic verdict, ask the human whether to notify a pre-saved contact. Send only a fixed notice; never page text, a signed viewer URL or a caller-selected destination. Decline/cancel/failure sends nothing. | Verify contact consent and SES identities, account/region access, delivery limits and human confirmation; define retention and abuse controls before connecting. |
| Bedrock orchestration | Model chooses among permitted tools and phrases immutable evidence. It cannot alter the verdict, bypass one-time consent or consume raw page text. Fail closed when model/provider or output validation fails. | Owner access/credit/quotas and an approved model; adversarial guard tests. Fixed sentences remain the functioning default. |
| Cognito OAuth | A reviewed OAuth authorization-code + PKCE S256 integration, audience/resource-bound tokens and protected-resource discovery could attach account identity to tools. Never substitute a transport session ID for authenticated identity. | Owner tenant, registered clients, redirects/scopes, token validation and conformance tests. Reconcile Alexa's documented 401/header limitations; do not silently change today's unauthenticated transport. |
| KayLerch Echo bridge | A separate Skill/agent adapter could host the existing tool contract and human elicitation on a real Echo. It must keep the same fail-closed output and consent gate. | Owner deploy/account permissions, license review, Bedrock/AgentCore access and actual-device tests. No bridge checkout, CDK run or cloud connection was made. |

These are not submission/demo features. The video may show a clearly labelled
planned branch, never a fake successful caregiver delivery or real Echo
connection. Any later implementation requires a separate task and security
review; this note makes no architecture change.
