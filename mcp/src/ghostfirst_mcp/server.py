"""GhostFirst MCP server: a safety gate for agents that are about to follow a link.

Tools:

* `check_link`: GhostFirst sends a disposable remote browser (a Wisp) to the
  link and returns the deterministic verdict with its evidence.
* `deep_check`: visits again as a phone, a computer, and another browser, and
  reports whether they were shown different things (cloaking).

Design rules:

* Deterministic rules decide; this server only reshapes the API result.
* No page-controlled free text (titles, page text, full URLs) is returned.
* One-time links (password resets, sign-in links) are never visited on the
  agent's say-so. The server detects them before sending anything, asks the
  human through MCP elicitation, and refuses when the client cannot ask. The
  agent has no argument that could confirm on the human's behalf.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union
from urllib.parse import urlsplit

from mcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from mcp.server.mcpserver import Context, Elicit, MCPServer, Resolve
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from . import texts
from .api import GhostFirstClient, GhostFirstError, api_url_from_env
from .sensitive import one_time_link_indicators

State = Literal["do_not_continue", "caution", "no_obvious_danger"]
Status = Literal["checked", "needs_human_confirmation", "declined_by_human", "error"]

INSTRUCTIONS = (
    "Call check_link before opening, following, summarizing by visiting, or submitting "
    "anything to a link you did not create, especially links from emails, messages, QR "
    "codes, or web pages. Follow `agent_guidance`. Never retry a one-time link "
    "yourself: only the human can confirm it."
)

SENSITIVE_CODE = "one_time_link_confirmation_required"


class Reason(BaseModel):
    code: str
    severity: str
    text: str


class LinkCheck(BaseModel):
    status: Status
    verdict: Optional[State] = None
    agent_guidance: str
    summary: Optional[str] = None
    reasons: list[Reason] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    final_host: Optional[str] = None
    redirects: int = 0
    requested: list[str] = Field(default_factory=list, description="Sensitive inputs the page asked for.")
    page_changed_after_load: bool = False
    recommended_next_step: Optional[Literal["deep_check"]] = None
    error_code: Optional[str] = None
    retry_after_seconds: Optional[int] = None
    not_a_guarantee: str = texts.NOT_A_GUARANTEE
    untrusted_data_notice: str = texts.UNTRUSTED


class VisitorProfile(BaseModel):
    profile: str
    final_host: Optional[str] = None
    reached_page: bool
    requested: list[str] = Field(default_factory=list)


class DeepCheck(BaseModel):
    status: Status
    verdict: Optional[State] = None
    agent_guidance: str
    comparison: Optional[str] = None
    comparison_detail: Optional[str] = None
    differences: list[str] = Field(default_factory=list)
    visitors: list[VisitorProfile] = Field(default_factory=list)
    reasons: list[Reason] = Field(default_factory=list)
    error_code: Optional[str] = None
    retry_after_seconds: Optional[int] = None
    not_a_guarantee: str = texts.NOT_A_GUARANTEE
    untrusted_data_notice: str = texts.UNTRUSTED


class HumanConfirmation(BaseModel):
    visit_anyway: bool = Field(description="Visit this possibly one-time link even though it may use it up?")


def _host(url: Optional[str]) -> Optional[str]:
    """ASCII (punycode) host only, so look-alike characters stay visible."""
    if not url:
        return None
    host = urlsplit(url).hostname
    if not host:
        return None
    try:
        return host.encode("idna").decode("ascii")
    except UnicodeError:
        return host


def _fill(template: str, params: dict[str, Any]) -> str:
    class Missing(dict):
        def __missing__(self, key: str) -> str:
            return "—"

    return template.format_map(Missing({k: str(v) for k, v in params.items()}))


def _reasons(verdict: dict[str, Any]) -> list[Reason]:
    out = []
    for finding in verdict.get("reasons", []):
        template = texts.FINDINGS.get(finding.get("code", ""))
        text = _fill(template, finding.get("params", {})) if template else "Additional evidence."
        out.append(Reason(code=finding.get("code", ""), severity=finding.get("severity", "info"), text=text))
    return out


def _requested(forms: dict[str, Any]) -> list[str]:
    names = [("password", "password"), ("otp", "verification_code"),
             ("payment", "payment"), ("email_or_username", "sign_in"), ("file_upload", "file_upload")]
    return [name for key, name in names if forms.get(key)]


def _summary(verdict: dict[str, Any]) -> str:
    params = dict(verdict.get("summary_params", {}))
    params["credential"] = texts.CREDENTIALS.get(params.get("credential", ""), texts.CREDENTIALS["generic"])
    template = texts.SUMMARIES.get(verdict.get("summary_code", ""), texts.SUMMARIES["nothing_observed"])
    return _fill(template, params)


def link_check_from_scan(result: dict[str, Any]) -> LinkCheck:
    verdict = result.get("verdict") or {"state": result.get("risk", {}).get("state", "caution")}
    state = verdict.get("state", "caution")
    timeline = result.get("visual_timeline") or {}
    next_step = (result.get("next_step") or {}).get("action")
    return LinkCheck(
        status="checked",
        verdict=state,
        agent_guidance=texts.GUIDANCE.get(state, texts.GUIDANCE["caution"]),
        summary=_summary(verdict),
        reasons=_reasons(verdict),
        rules=verdict.get("rules", []),
        final_host=_host(result.get("final_url")),
        redirects=max(0, len(result.get("redirect_chain", [])) - 1),
        requested=_requested(result.get("forms", {})),
        page_changed_after_load=bool(timeline.get("transformation")),
        recommended_next_step="deep_check" if next_step == "deep_check" else None,
    )


def deep_check_from_result(result: dict[str, Any]) -> DeepCheck:
    verdict = result.get("verdict") or {}
    state = verdict.get("state", "caution")
    comparison = result.get("comparison", {})
    title, detail = texts.COMPARISONS.get(comparison.get("classification", ""), (None, None))
    differences = [
        texts.DIFFERENCES[d["type"]] for d in comparison.get("differences", []) if d.get("type") in texts.DIFFERENCES
    ]
    visitors = []
    for wisp in result.get("wisps", []):
        scan = wisp.get("result")
        visitors.append(VisitorProfile(
            profile=wisp.get("profile", "unknown"),
            final_host=_host(scan.get("final_url")) if scan else None,
            reached_page=scan is not None,
            requested=_requested(scan.get("forms", {})) if scan else [],
        ))
    return DeepCheck(
        status="checked",
        verdict=state,
        agent_guidance=texts.GUIDANCE.get(state, texts.GUIDANCE["caution"]),
        comparison=title,
        comparison_detail=detail,
        differences=differences,
        visitors=visitors,
        reasons=_reasons(verdict),
    )


def _error_guidance(code: str) -> str:
    if code in {"rate_limited", "server_busy"}:
        return "GhostFirst is busy. Wait and try again later; do not open the link meanwhile."
    if code in {"invalid_url", "blocked_destination"}:
        return "GhostFirst refused this address (invalid, private, or local). Do not open it."
    return "GhostFirst could not check this link. Do not open it; tell the user it could not be checked."


class NoQuestion(BaseModel):
    """Resolver outcome when the human was not asked."""

    reason: Literal["not_one_time", "client_cannot_ask"]


# Explicit members, so the framework injects the full outcome (a decline is
# an answer, not an error) alongside the "not asked" case.
Consent = Union[NoQuestion, AcceptedElicitation[HumanConfirmation], DeclinedElicitation, CancelledElicitation]


async def one_time_consent(url: str, ctx: Context) -> Union[NoQuestion, Elicit[HumanConfirmation]]:
    """Ask the human only for links that look one-time, before anything is sent."""
    if not one_time_link_indicators(url):
        return NoQuestion(reason="not_one_time")
    capabilities = ctx.client_capabilities
    if capabilities is None or capabilities.elicitation is None:
        return NoQuestion(reason="client_cannot_ask")
    return Elicit(
        "This link looks like a one-time link (password reset, sign-in, or invitation). "
        "Checking it may use it up. Should GhostFirst visit it anyway?",
        HumanConfirmation,
    )


def _unwrap(consent: Consent) -> Consent:
    # A resolver that returns a value instead of asking arrives wrapped as "accepted".
    if isinstance(consent, AcceptedElicitation) and isinstance(consent.data, NoQuestion):
        return consent.data
    return consent


def _confirmed(consent: Consent) -> Optional[bool]:
    """True: the human accepted. False: declined or cancelled. None: not asked."""
    if isinstance(consent, NoQuestion):
        return None
    return isinstance(consent, AcceptedElicitation) and bool(consent.data.visit_anyway)


def build_server(client: Optional[GhostFirstClient] = None) -> MCPServer:
    client = client or GhostFirstClient(api_url_from_env())
    server = MCPServer(
        name="ghostfirst",
        title="GhostFirst link check",
        instructions=INSTRUCTIONS,
        version="0.1.0",
    )
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)

    async def run(kind: str, url: str, consent: Consent):
        call = client.scan if kind == "scan" else client.deep_check
        shape = link_check_from_scan if kind == "scan" else deep_check_from_result
        model = LinkCheck if kind == "scan" else DeepCheck
        consent = _unwrap(consent)
        confirmed = _confirmed(consent)
        not_visited = (
            "This looks like a one-time link. It was not visited. Ask the user to check it "
            "themselves in the GhostFirst app or web page; do not open it for them."
        )
        if confirmed is False or (isinstance(consent, NoQuestion) and consent.reason == "client_cannot_ask"):
            return model(
                status="declined_by_human" if confirmed is False else "needs_human_confirmation",
                agent_guidance=not_visited, error_code=SENSITIVE_CODE,
            )
        try:
            return shape(await call(url, confirm_sensitive_link=confirmed is True))
        except GhostFirstError as error:
            if error.code == SENSITIVE_CODE:
                # The API's rules caught a link the local rules did not.
                return model(status="needs_human_confirmation", agent_guidance=not_visited,
                             error_code=SENSITIVE_CODE)
            return model(status="error", agent_guidance=_error_guidance(error.code),
                         error_code=error.code, retry_after_seconds=error.retry_after_seconds)

    @server.tool(annotations=read_only)
    async def check_link(
        url: str, consent: Annotated[Consent, Resolve(one_time_consent)]
    ) -> LinkCheck:
        """Check a link with GhostFirst BEFORE opening or following it.

        A disposable remote browser visits the link away from this machine and the
        user's device. Returns a deterministic verdict (do_not_continue, caution,
        no_obvious_danger), the evidence behind it, and guidance for the agent.
        Takes about 5-10 seconds. The link is sent to the GhostFirst service."""
        return await run("scan", url, consent)

    @server.tool(annotations=read_only)
    async def deep_check(
        url: str, consent: Annotated[Consent, Resolve(one_time_consent)]
    ) -> DeepCheck:
        """Visit a link as three different visitors (phone, computer, another browser)
        and report whether the site showed them different things (cloaking). Use it
        when check_link recommends it or the user wants a deeper look. Takes about
        10-20 seconds."""
        return await run("deep", url, consent)

    return server


def main() -> None:
    build_server().run("stdio")


if __name__ == "__main__":
    main()
