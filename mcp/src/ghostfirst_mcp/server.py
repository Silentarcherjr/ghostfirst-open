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

import argparse
import functools
import inspect
import ipaddress
import math
import re
import asyncio
from pathlib import Path
from typing import Annotated, Any, Literal, Optional, Sequence, Union
from urllib.parse import urlsplit

from mcp.server.elicitation import AcceptedElicitation, CancelledElicitation, DeclinedElicitation
from mcp.server.mcpserver import Context, Elicit, MCPServer, Resolve
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response

from . import texts, ui
from .api import GhostFirstClient, GhostFirstError, api_url_from_env
from .inbox import Inbox
from .jobs import JOB_TIMEOUT, Jobs
from .sensitive import one_time_link_indicators

State = Literal["do_not_continue", "caution", "no_obvious_danger"]
Status = Literal["shared", "checking", "checked", "needs_human_confirmation", "declined_by_human", "error"]

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
    locale: str = "en-US"
    status: Status
    job_id: Optional[str] = None
    verdict: Optional[State] = None
    agent_guidance: str
    summary: Optional[str] = None
    reasons: list[Reason] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    final_host: Optional[str] = None
    redirects: int = 0
    requested: list[str] = Field(default_factory=list, description="Sensitive inputs the page asked for.")
    checked_earlier_today: bool = False
    history_note: Optional[str] = None
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


class DeepCheck(LinkCheck):
    status: Status
    job_id: Optional[str] = None
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


# Display vocabulary only: copied registry names grant no trust credit.
BRANDS = ('Banco General', 'Banistmo', 'BAC Credomatic', 'Caja de Ahorros', 'Banco Nacional de Panamá', 'Global Bank', 'Multibank', 'Credicorp Bank', 'PayPal', 'Microsoft', 'Apple', 'Google', 'Netflix', 'Amazon', 'Facebook', 'Instagram', 'WhatsApp', 'Mercado Libre', 'Mercado Pago', 'DHL', 'FedEx', 'UPS')
RULES = {f"CAU-{i}" for i in range(10)} | {f"DNC-{i}" for i in range(1, 5)} | {"NSB-0"}
PROFILES = {"android_mobile", "desktop_chrome", "desktop_firefox"}

def _domain(value):
    if not isinstance(value, str) or not value or len(value) > 253:
        return None
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    try:
        host = value.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        return None
    if len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in host.split(".")):
        return None
    return host

def _host(url: Optional[str]) -> Optional[str]:
    """ASCII host only. Invalid addresses never fall back to raw text."""
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
        return _domain(parsed.hostname) if parsed.scheme in {"http", "https"} else None
    except ValueError:
        return None

def _fill(template: str, params: dict[str, Any]) -> str:
    class Missing(dict):
        def __missing__(self, key):
            return "—"
    safe = {}
    for key, value in params.items():
        if key in {"domain", "host", "from_domain", "brand_domain", "shortener"}:
            safe[key] = _domain(value) or "—"
        elif key == "brand":
            safe[key] = value if isinstance(value, str) and value in BRANDS else "—"
        elif key in {"count", "seconds", "changed"}:
            safe[key] = str(value) if type(value) in {int, float} and math.isfinite(value) and 0 <= value <= 1000000 else "—"
        elif key == "credential":
            # Only fixed EN/ES credential labels may enter a sentence.
            safe[key] = value if isinstance(value, str) and value in {*texts.CREDENTIALS.values(), *texts.ES_CREDENTIALS.values()} else "—"
    return template.format_map(Missing(safe))

def _reasons(verdict: dict[str, Any], locale="en-US") -> list[Reason]:
    out = []
    for finding in verdict.get("reasons", []):
        template = texts.table("FINDINGS", locale).get(finding.get("code", ""))
        text = _fill(template, finding.get("params", {})) if template else texts.fixed("Additional evidence.", locale)
        out.append(Reason(code=finding["code"] if finding.get("code") in texts.FINDINGS else "unknown_evidence", severity=finding.get("severity") if finding.get("severity") in {"high", "medium", "low", "info"} else "info", text=text))
    return out


def _requested(forms: dict[str, Any]) -> list[str]:
    names = [("password", "password"), ("otp", "verification_code"),
             ("payment", "payment"), ("email_or_username", "sign_in"), ("file_upload", "file_upload")]
    return [name for key, name in names if forms.get(key)]


def _summary(verdict: dict[str, Any], locale="en-US") -> str:
    params = dict(verdict.get("summary_params", {}))
    params["credential"] = texts.table("CREDENTIALS", locale).get(params.get("credential", ""), texts.table("CREDENTIALS", locale)["generic"])
    template = texts.table("SUMMARIES", locale).get(verdict.get("summary_code", ""), texts.table("SUMMARIES", locale)["nothing_observed"])
    return _fill(template, params)


def link_check_from_scan(result: dict[str, Any], locale="en-US") -> LinkCheck:
    verdict = result.get("verdict") or {"state": result.get("risk", {}).get("state", "caution")}
    state = verdict.get("state", "caution")
    timeline = result.get("visual_timeline") or {}
    next_step = (result.get("next_step") or {}).get("action")
    return LinkCheck(
        status="checked",
        verdict=state,
        agent_guidance=texts.table("GUIDANCE", locale).get(state, texts.table("GUIDANCE", locale)["caution"]),
        summary=_summary(verdict, locale),
        reasons=_reasons(verdict, locale),
        rules=[r for r in verdict.get("rules", []) if isinstance(r, str) and r in RULES],
        final_host=_host(result.get("final_url")),
        redirects=max(0, len(result.get("redirect_chain", [])) - 1),
        requested=_requested(result.get("forms", {})),
        page_changed_after_load=bool(timeline.get("transformation")),
        recommended_next_step="deep_check" if next_step == "deep_check" else None,
    )


def deep_check_from_result(result: dict[str, Any], locale="en-US") -> DeepCheck:
    verdict = result.get("verdict") or {}
    state = verdict.get("state", "caution")
    comparison = result.get("comparison", {})
    title, detail = texts.table("COMPARISONS", locale).get(comparison.get("classification", ""), (None, None))
    differences = [
        texts.table("DIFFERENCES", locale)[d["type"]] for d in comparison.get("differences", []) if d.get("type") in texts.DIFFERENCES
    ]
    visitors = []
    for wisp in result.get("wisps", []):
        scan = wisp.get("result")
        visitors.append(VisitorProfile(
            profile=wisp.get("profile") if wisp.get("profile") in PROFILES else "unknown",
            final_host=_host(scan.get("final_url")) if scan else None,
            reached_page=scan is not None,
            requested=_requested(scan.get("forms", {})) if scan else [],
        ))
    return DeepCheck(
        status="checked",
        verdict=state,
        agent_guidance=texts.table("GUIDANCE", locale).get(state, texts.table("GUIDANCE", locale)["caution"]),
        comparison=title,
        comparison_detail=detail,
        differences=differences,
        visitors=visitors,
        reasons=_reasons(verdict, locale),
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


def client_locale(ctx):
    meta = ctx.request_context.meta
    value = meta.get("locale", "") if isinstance(meta, dict) else (meta.model_extra or {}).get("locale", "") if meta else ""
    return "es-US" if isinstance(value, str) and value.lower().startswith("es") else "en-US"

def localized_tool(fn):
    signature = inspect.signature(fn)
    @functools.wraps(fn)
    async def wrapped(*args, **kwargs):
        ctx = signature.bind(*args, **kwargs).arguments["ctx"]
        out = await fn(*args, **kwargs)
        # Completed jobs retain their originating locale when polled.
        locale = out.locale if out.status == "checked" else client_locale(ctx)
        out.locale = locale
        for field in ("agent_guidance", "history_note"):
            setattr(out, field, texts.fixed(getattr(out, field), locale))
        out.not_a_guarantee = texts.table("NOT_A_GUARANTEE", locale)
        out.untrusted_data_notice = texts.table("UNTRUSTED", locale)
        return out
    return wrapped

async def one_time_consent(url: str, ctx: Context) -> Union[NoQuestion, Elicit[HumanConfirmation]]:
    """Ask the human only for links that look one-time, before anything is sent."""
    if not one_time_link_indicators(url):
        return NoQuestion(reason="not_one_time")
    capabilities = ctx.client_capabilities
    if capabilities is None or capabilities.elicitation is None:
        return NoQuestion(reason="client_cannot_ask")
    return Elicit(
        texts.fixed(texts.CONSENT, client_locale(ctx)),
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
    jobs = Jobs()
    server = MCPServer(
        name="ghostfirst",
        title="GhostFirst link check",
        instructions=INSTRUCTIONS,
        version="0.1.0",
        extensions=[ui.Apps()],
    )
    read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=True)

    def connection(ctx: Context):
        # MCP 2.2.0's high-level Context exposes a per-request proxy. This
        # pinned-SDK adapter uses its verified Connection; never trust a
        # client-supplied header, client name, or caller-supplied session id.
        if ctx.protocol_version not in {"2025-11-25", "2025-06-18", "2024-11-05"}:
            return None
        owner = getattr(ctx.session, "_connection", None)
        if owner is not None and "ghostfirst_jobs" not in owner.state:
            owner.state["ghostfirst_jobs"] = True
            owner.exit_stack.push_async_callback(jobs.close_owner, owner)
            owner.state["ghostfirst_inbox"] = Inbox()
            owner.exit_stack.callback(owner.state["ghostfirst_inbox"].clear)
        return owner

    async def run(kind: str, url: str, consent: Consent, ctx: Context):
        locale = client_locale(ctx)
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
        owner = connection(ctx)
        if owner is None:
            return model(status="error", agent_guidance=_error_guidance("unknown_error"), error_code="session_required")

        async def work():
            try:
                result = await asyncio.wait_for(call(url, confirm_sensitive_link=confirmed is True), JOB_TIMEOUT)
                shaped = shape(result, locale)
                shaped.locale = locale
                host = shaped.final_host or next((v.final_host for v in getattr(shaped, "visitors", []) if v.final_host), None)
                shaped.checked_earlier_today = owner.state["ghostfirst_inbox"].remember(host)
                if shaped.checked_earlier_today:
                    shaped.history_note = "You checked this site earlier today. This is a fresh check, not a guarantee."
                return shaped
            except GhostFirstError as error:
                if error.code == SENSITIVE_CODE:
                    return model(status="needs_human_confirmation", agent_guidance=not_visited, error_code=SENSITIVE_CODE)
                return model(status="error", agent_guidance=_error_guidance(error.code),
                             error_code=error.code, retry_after_seconds=error.retry_after_seconds)
            except Exception:
                # Invalid JSON/schema, timeout, or unexpected provider errors never
                # leak exception text and never become a calm verdict.
                return model(status="error", agent_guidance=_error_guidance("unknown_error"), error_code="check_failed")

        job_id = jobs.start(owner, work)
        if not job_id:
            return model(status="error", agent_guidance=_error_guidance("server_busy"), error_code="server_busy")
        await ctx.report_progress(0, 1, texts.fixed("Check queued. Do not open the link while checking.", client_locale(ctx)))
        return model(status="checking", job_id=job_id,
                     agent_guidance="The check is running. Poll get_check_result with this job_id. Do not open the link yet.")

    @server.tool(annotations=read_only, meta={"ui": {"resourceUri": ui.URI}})
    @localized_tool
    async def check_link(
        url: str, consent: Annotated[Consent, Resolve(one_time_consent)], ctx: Context
    ) -> LinkCheck:
        """Check a link with GhostFirst BEFORE opening or following it.

        A disposable remote browser visits the link away from this machine and the
        user's device. Returns a deterministic verdict (do_not_continue, caution,
        no_obvious_danger), the evidence behind it, and guidance for the agent.
        Returns checking and a job_id immediately; poll get_check_result. The actual
        visit takes seconds. The link is sent to the GhostFirst service."""
        return await run("scan", url, consent, ctx)

    @server.tool(annotations=read_only, meta={"ui": {"resourceUri": ui.URI}})
    @localized_tool
    async def deep_check(
        url: str, consent: Annotated[Consent, Resolve(one_time_consent)], ctx: Context
    ) -> DeepCheck:
        """Visit a link as three different visitors (phone, computer, another browser)
        and report whether the site showed them different things (cloaking). Use it
        when check_link recommends it or the user wants a deeper look. Takes about
        seconds to finish, but returns a job_id immediately; poll get_check_result."""
        return await run("deep", url, consent, ctx)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False), meta={"ui": {"resourceUri": ui.URI}})
    @localized_tool
    async def get_check_result(job_id: str, ctx: Context) -> DeepCheck:
        """Poll a check started in this MCP session. Checking is not a verdict.
        Results expire after 15 minutes; unknown, expired, and other-session
        jobs all return the same error. Never open a link while checking."""
        job = jobs.get(connection(ctx), job_id)
        if job is None:
            return DeepCheck(status="error", agent_guidance=_error_guidance("unknown_error"), error_code="job_not_found")
        await ctx.report_progress(1 if job.result else 0, 1, texts.fixed("Check complete." if job.result else "Still checking.", client_locale(ctx)))
        return DeepCheck.model_validate(job.result.model_dump()) if job.result else DeepCheck(status="checking", job_id=job_id,
                                     agent_guidance="Still checking. Poll again; do not open the link yet.")

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False),
                 meta={"ui": {"visibility": ["app"]}})
    @localized_tool
    async def share_link(url: str, ctx: Context) -> LinkCheck:
        """App-only inbox ingestion after a human presses Share. Stores the link
        in this MCP session for 15 minutes; does not visit it or grant consent."""
        owner = connection(ctx)
        if owner is None or not owner.state["ghostfirst_inbox"].share(url):
            return LinkCheck(status="error", agent_guidance=_error_guidance("invalid_url"), error_code="invalid_url")
        return LinkCheck(status="shared", agent_guidance="Link shared to this session. Ask check_shared_link to check it; do not open it yet.")

    @server.tool(annotations=read_only, meta={"ui": {"resourceUri": ui.URI}})
    @localized_tool
    async def check_shared_link(ctx: Context) -> LinkCheck:
        """Check the latest link the human shared to this session, without URL
        dictation. One-time links need human elicitation before a job starts.
        No shared link or an expired inbox fails closed."""
        owner = connection(ctx)
        url = owner.state["ghostfirst_inbox"].latest() if owner else None
        if not url:
            return LinkCheck(status="error", agent_guidance="No shared link is available. Ask the human to share one; do not open anything.", error_code="no_shared_link")
        # Snapshot before awaiting consent: a later Share cannot replace the
        # address for which the human is answering.
        consent = NoQuestion(reason="not_one_time")
        if one_time_link_indicators(url):
            caps = ctx.client_capabilities
            if caps is None or caps.elicitation is None:
                consent = NoQuestion(reason="client_cannot_ask")
            else:
                consent = await ctx.elicit(
                    texts.fixed(texts.CONSENT, client_locale(ctx)),
                    HumanConfirmation,
                )
        return await run("scan", url, consent, ctx)

    @server.resource(ui.URI, mime_type=ui.MIME, meta=ui.META)
    def verdict_card():
        return ui.HTML

    return server


SIMULATOR_DIR = Path(__file__).parent / "simulator"
SIMULATOR_FILES = {"index.html": "text/html", "app.js": "text/javascript", "styles.css": "text/css"}
# Same-origin only: the page talks to /mcp on its own host and loads nothing else.
SIMULATOR_HEADERS = {
    "Content-Security-Policy": (
        f"default-src 'none'; script-src 'self' {ui.SCRIPT_HASH}; style-src 'self' {ui.STYLE_HASH}; connect-src 'self'; frame-src 'self'; "
        "img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def build_http_app(
    client: Optional[GhostFirstClient] = None,
    *,
    host: str = "127.0.0.1",
    allowed_hosts: Sequence[str] = (),
    simulator: bool = True,
) -> Starlette:
    """Streamable HTTP app: MCP at `/mcp`, plus the voice-assistant simulator at `/`.

    Stateful sessions, so a one-time link can still be confirmed by the human
    (the elicitation request travels on the open `tools/call` stream).
    """
    server = build_server(client)
    if simulator:
        def page(name: str):
            async def handler(request: Request) -> Response:
                body = (SIMULATOR_DIR / name).read_bytes()
                return Response(body, media_type=SIMULATOR_FILES[name], headers=SIMULATOR_HEADERS)
            return handler

        for name in SIMULATOR_FILES:
            path = "/" if name == "index.html" else f"/{name}"
            server.custom_route(path, methods=["GET"])(page(name))
    security = None
    if allowed_hosts:
        # Public deployment: name every Host the server answers to, and accept
        # browser requests only from those same origins.
        security = TransportSecuritySettings(
            allowed_hosts=list(allowed_hosts),
            allowed_origins=[f"https://{h}" for h in allowed_hosts],
        )
    return server.streamable_http_app(host=host, transport_security=security)


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(prog="ghostfirst-mcp", description=__doc__.splitlines()[0])
    parser.add_argument("--http", action="store_true", help="serve Streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8780)
    parser.add_argument("--allowed-host", action="append", default=[], metavar="HOST",
                        help="public Host header to accept (repeatable); required off localhost")
    parser.add_argument("--no-simulator", action="store_true", help="do not serve the simulator page")
    args = parser.parse_args(argv)
    if not args.http:
        build_server().run("stdio")
        return
    local = args.host in ("127.0.0.1", "localhost", "::1")
    if not local and not args.allowed_host:
        parser.error("--allowed-host is required when binding to a non-local address")
    import uvicorn

    app = build_http_app(host=args.host, allowed_hosts=args.allowed_host, simulator=not args.no_simulator)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
